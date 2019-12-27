import asyncio
import re
from pathlib import Path
from typing import Dict, Tuple, Optional
from datetime import datetime

import requests
from requests.exceptions import ConnectionError
from aiogram.types import ContentType, Message as BotMessage
from aiohttp import BasicAuth, ClientSession, FormData
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from peewee import SqliteDatabase, Model, BooleanField, CharField
from PIL import Image

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


@dp.message_handler(commands=['delete', 'del'])
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
    Для анонимной пересылки сообщения в озонач просто отправьте текст боту. В ответ вернётся timestamp сообщения: 
    используя его с помощью команды /delete можно удалить это сообщение. Пример команды: 
    /delete `1573423678.482000`
    
    Имеется возможность анонимной пересылки изображений. Отправлять нужно по одному фото.
    
    Бот по прежнему не хранит и не логирует никакие личные данные кроме времени сообщения (исключительно время, 
    без текста и без автора) и текста ошибок (интересны для статистики и отладки соответственно).
    """
    await message.reply(help_message, parse_mode='Markdown')


def get_photo_message_ts(data: Dict) -> str:
    return data['file']['shares']['private'][OZONACH_CHANNEL][0]['ts']


def is_reply(message_text: str) -> Tuple[Optional[str], Optional[str]]:
    result = re.search(r'(?<=https://ozon.slack.com/archives/)(\w+/p\d+)', message_text)
    if result:
        channel_token, message_ts = result.group(0).split('/')
        # cut link to thread
        new_message_text = re.sub(r'(https://ozon.slack.com/archives/\w+/p\d+(\?[\S]+)?)', '', message_text)

        # p1234567890123456 -> 1234567890.123456
        buf = message_ts.lstrip('p')
        thread_ts = buf[:-6] + '.' + buf[-6:]

        return thread_ts, new_message_text
    return None, None


def webp_to_png(webp_file_path: Path) -> Path:
    img = Image.open(webp_file_path)
    img.convert('RGBA')
    png_file_path = webp_file_path.parent / (webp_file_path.stem + '.png')
    img.save(png_file_path, 'png')

    return png_file_path


async def send_media(message: BotMessage, local_file_path: Path):
    data = {
        'token': SLACK_BOT_TOKEN,
        "channels": OZONACH_CHANNEL,
        'initial_comment': message.caption if message.caption else ''
    }
    async with ClientSession() as session:
        form = FormData(data)
        form.add_field('file', open(local_file_path, 'rb'))

        async with session.post('https://slack.com/api/files.upload', data=form) as response:
            response_data = await response.json()

            if response_data['ok']:
                photo_message_ts = get_photo_message_ts(response_data)
                await message.reply(f'`{photo_message_ts}`', parse_mode='Markdown')
                Message.create(ts=float(photo_message_ts), success=True)
            else:
                Message.create(ts=datetime.now().timestamp(), success=False)


@dp.message_handler(content_types=[ContentType.STICKER])
async def sticker_handler(message: BotMessage):
    file_id = message.sticker.thumb.file_id  # message.sticker.file_id -- full size
    local_file_name = Path(f'./files/{file_id}.webp')
    await bot.download_file_by_id(file_id=file_id, destination=local_file_name)
    png_file_path = webp_to_png(local_file_name)
    await send_media(message, png_file_path)
    png_file_path.unlink()


@dp.message_handler(content_types=[ContentType.PHOTO])
async def post_photo(message: BotMessage):
    file_id = message.photo[-1].file_id
    local_file_path = Path(f'./files/{file_id}.jpeg')
    await bot.download_file_by_id(file_id=file_id, destination=local_file_path)
    await send_media(message, local_file_path)
    local_file_path.unlink()


@dp.message_handler(content_types=[ContentType.TEXT])
async def post_message(message: BotMessage):
    async with ClientSession(headers=HEADERS) as session:
        data = {
            "channel": OZONACH_CHANNEL,
            "text": message.text,
            'initial_comment': message.caption if message.caption else ''
        }

        thread_ts, message_text = is_reply(message.text)
        if thread_ts:
            data['text'] = message_text
            data['thread_ts'] = thread_ts
            data['reply_broadcast'] = True

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
