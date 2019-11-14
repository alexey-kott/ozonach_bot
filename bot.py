import asyncio
from pathlib import Path
from typing import Dict
from datetime import datetime

import requests
from requests.exceptions import ConnectionError
from aiogram.types import ContentType, Message as BotMessage
from aiohttp import BasicAuth, ClientSession, FormData
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from peewee import SqliteDatabase, Model, BooleanField, CharField

from config import BOT_TOKEN, SLACK_AUTH_HEADER, SLACK_BOT_TOKEN, OZONACH_CHANNEL, \
    PROXY_HOST, PROXY_PORT, PROXY_USERNAME, PROXY_PASS

try:
    PROXY_AUTH = None
    PROXY_URL = None
    requests.get('https://api.telegram.org', timeout=1)
except ConnectionError as e:
    PROXY_URL = f"socks5://{PROXY_HOST}:{PROXY_PORT}"
    PROXY_AUTH = BasicAuth(login=PROXY_USERNAME, password=PROXY_PASS)

bot = Bot(token=BOT_TOKEN, proxy=PROXY_URL, proxy_auth=PROXY_AUTH)
dp = Dispatcher(bot)
db = SqliteDatabase('ozonach.db')

HEADERS = {
    "Content-type": "application/json;charset=utf-8",
    "Authorization": SLACK_AUTH_HEADER
}


class Message(Model):
    class Meta:
        database = db

    ts = CharField()
    success = BooleanField()


@dp.message_handler(commands=['start'])
async def start(message: BotMessage):
    await message.reply("You can send me a message and I will forward it to 03ch anonymously")


@dp.message_handler(commands=['init'])
async def init(message: BotMessage):
    files_dir = Path('./files')
    files_dir.mkdir(exist_ok=True)
    Message.create_table(fail_silently=True)
    await message.reply('Initialization completed')


@dp.message_handler(commands=['ping'])
async def ping(message: BotMessage):
    await message.reply("I'm alive")


@dp.message_handler(commands=['source'])
async def get_source_link(message: BotMessage):
    await message.reply("https://github.com/Alex-Kott/ozonach_bot")


@dp.message_handler(commands=['delete'])
async def delete_message(message: BotMessage):
    command, ts = message.text.split(' ')
    async with ClientSession(headers=HEADERS) as session:
        data = {
            "channel": OZONACH_CHANNEL,
            "ts": ts
        }
        async with session.post('https://slack.com/api/chat.delete', json=data) as response:
            response_data = await response.json()
            if response_data['ok']:
                await message.reply('Message deleted')
            else:
                await message.reply('Message was not deleted')
                print(response_data)


@dp.message_handler(commands=['help'])
async def get_help(message: BotMessage):
    help_message = """
    Для анонимной пересылки сообщения в озонач просто отправьте текст боту. В ответ вернётся timestamp сообщения: используя его с помощью команды /delete можно удалить это сообщение. Пример команды: 
    /delete `1573423678.482000`
    
    Имеется возможность анонимной пересылки изображений. Отправлять нужно по одному фото.
    
    Бот по прежнему не хранит и не логирует никакие личные данные кроме времени сообщения (исключительно время, без текста и без автора) и текста ошибок (интересны для статистики и отладки соответственно).
    """
    await message.reply(help_message, parse_mode='Markdown')


def get_photo_message_ts(data: Dict) -> str:
    return data['file']['shares']['private'][OZONACH_CHANNEL][0]['ts']


@dp.message_handler(content_types=[ContentType.PHOTO])
async def post_photo(message: BotMessage):
    file_id = message.photo[0].file_id
    local_file_name = Path(f'./files/{file_id}.jpg')
    await bot.download_file_by_id(file_id=file_id, destination=local_file_name)

    async with ClientSession() as session:
        data = {
            'token': SLACK_BOT_TOKEN,
            "channels": OZONACH_CHANNEL
        }
        form = FormData(data)
        form.add_field('file', open(local_file_name, 'rb'))

        async with session.post('https://slack.com/api/files.upload', data=form) as response:
            response_data = await response.json()

            if response_data['ok']:
                photo_message_ts = get_photo_message_ts(response_data)
                await message.reply(f'`{photo_message_ts}`', parse_mode='Markdown')
                Message.create(ts=float(photo_message_ts), success=True)
            else:
                Message.create(ts=datetime.now().timestamp(), success=False)
            local_file_name.unlink()


@dp.message_handler(content_types=[ContentType.TEXT, ContentType.PHOTO])
async def post_message(message: BotMessage):
    async with ClientSession(headers=HEADERS) as session:
        data = {
            "channel": OZONACH_CHANNEL,
            "text": message.text
        }
        async with session.post('https://slack.com/api/chat.postMessage', json=data) as response:
            response_data = await response.json()
            if response_data['ok']:
                await message.reply(f'`{response_data["ts"]}`', parse_mode='Markdown')
                Message.create(ts=response_data['ts'], success=True)
            else:
                await message.reply('Something went wrong')
                Message.create(ts=datetime.now().timestamp(), success=False)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    executor.start_polling(dp)
