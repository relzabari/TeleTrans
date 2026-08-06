from telethon import TelegramClient, events
from deep_translator import GoogleTranslator
from langdetect import detect
from dotenv import load_dotenv
import os,json
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    MessageMediaWebPage
)

load_dotenv()
cfg=json.load(open("config.json","r",encoding="utf8"))
client=TelegramClient("session/session",int(os.getenv("API_ID")),os.getenv("API_HASH"))

@client.on(events.NewMessage(chats=cfg["source_channels"]))
async def handler(event):
    try:
        txt=event.raw_text or ""
        if not txt: return
        try:
            if detect(txt)!="ar":
                return
        except:
            pass

        chat = await event.get_chat()
        title = chat.title
        tr=GoogleTranslator(source="ar",target="iw").translate(txt)
        message = (
        f"מקור: {title}\n\n"
        f"{tr}\n\n"
        f"────────────────────\n\n"
        f"🇸🇦 מקור\n\n"
        f"{txt}")
    
        
        if isinstance(event.media, (MessageMediaPhoto, MessageMediaDocument)):
            path = await event.download_media()
            await client.send_file(
            cfg["destination"],
            path,
            caption=message)
            
            import os
            os.remove(path)
            
        else:
            await client.send_message(
            cfg["destination"],
            message)
    except Exception as e:
        import traceback
        traceback.print_exc()

async def main():
    await client.start(phone=os.getenv("PHONE"))
    print("Running...")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())
