import asyncio

import requests
from requests.exceptions import ConnectionError
from aiogram.types import ContentType, Message
from aiohttp import BasicAuth, ClientSession
from aiogram import Bot, Dispatcher
from aiogram.utils import executor

from config import BOT_TOKEN, SLACK_BOT_AUTH, OZONACH_CHANNEL, \
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

HEADERS = {
    "Content-type": "application/json;charset=utf-8",
    "Authorization": SLACK_BOT_AUTH
}


@dp.message_handler(commands=['start'])
async def start(message: Message):
    await message.reply("You can send me a message and I will forward it to 03ch anonymously")


@dp.message_handler(commands=['ping'])
async def ping(message: Message):
    await message.reply("I'm alive")


@dp.message_handler(commands=['delete'])
async def delete_message(message: Message):
    command, ts = message.text.split(' ')
    async with ClientSession(headers=HEADERS) as session:
        data = {
            "channel": "GD5M3VDL0",
            "ts": ts
        }
        async with session.post('https://slack.com/api/chat.delete', json=data) as response:
            response_data = await response.json()
            if response_data['ok']:
                await message.reply('Message deleted')
            else:
                await message.reply('Message was not deleted')
                print(response_data)


@dp.message_handler(content_types=[ContentType.TEXT])
async def post_message(message: Message):
    async with ClientSession(headers=HEADERS) as session:
        data = {
            "channel": OZONACH_CHANNEL,
            "text": message.text
        }
        async with session.post('https://slack.com/api/chat.postMessage', json=data) as response:
            response_data = await response.read()
            print(response_data)

    await message.reply(message.text)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    executor.start_polling(dp)
