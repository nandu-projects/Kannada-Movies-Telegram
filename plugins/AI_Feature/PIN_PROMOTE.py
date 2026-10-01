from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.types import *
from pyrogram import *


async def admin_check(message: Message) -> bool:
    if not message.from_user:
        return False

    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return False

    if message.from_user.id in [
        777000,  # Telegram Service Notifications
        1087968824  # GroupAnonymousBot
    ]:
        return True

    client = message._client
    chat_id = message.chat.id
    user_id = message.from_user.id

    check_status = await client.get_chat_member(
        chat_id=chat_id,
        user_id=user_id
    )
    admin_strings = [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]
    if check_status.status not in admin_strings:
        return False
    else:
        return True

async def admin_filter_f(filt, client, message):
    return await admin_check(message)

admin_fliter = filters.create(func=admin_filter_f, name="AdminFilter")


@Client.on_message(filters.command("pin") & admin_fliter)
async def pin(_, message: Message):
    if not message.reply_to_message:
        return
    await message.reply_to_message.pin()
    await message.reply_text("I Have Pinned That message")


@Client.on_message(filters.command("unpin") & admin_fliter)             
async def unpin(_, message: Message):
    if not message.reply_to_message:
        return
    await message.reply_to_message.unpin()
    await message.reply_text("I Have UnPinned That message")


@Client.on_message(filters.command("unpin_all") & filters.group)
async def unpinall_handler(client, message: Message):
    try:
     user = await client.get_chat_member(message.chat.id , message.from_user.id)
     if user.status not in [enums.ChatMemberStatus.OWNER , enums.ChatMemberStatus.ADMINISTRATOR]:
         raise PermissionError("You are not allowed to use this command")
     await client.unpin_all_chat_messages(message.chat.id)
    except Exception as e:
     await message.reply_text(f"{e}")

@Client.on_message(filters.command("promote") & filters.group)
async def promoting(client, message):
     global new_admin
     if not message.reply_to_message:
         return await message.reply("use this command reply")
     reply = message.reply_to_message
     chat_id = message.chat.id
     new_admin = reply.from_user
     admin = message.from_user
     user_stats = await client.get_chat_member(chat_id, admin.id)
     bot_stats = await client.get_chat_member(chat_id, "self")
     if not bot_stats.privileges:
         return await message.reply("hey dude iam not admin")
     elif not user_stats.privileges:
         return await message.reply("Sorry dude you need admin")
     elif not bot_stats.privileges.can_promote_members:
         return await message.reply("i dont have admin rights ")
     elif not user_stats.privileges.can_promote_members:
         return await message.reply("you need admin rights 😒")
     elif user_stats.privileges.can_promote_members:
          msg = await message.reply_text("Promoting")
          await client.promote_chat_member(
            message.chat.id,
            new_admin.id,
            privileges=pyrogram.types.ChatPrivileges(
            can_change_info=True,
            can_delete_messages=True,
            can_pin_messages=True,
            can_invite_users=True,
            can_manage_video_chats=True,
            can_restrict_members=True
))
          await msg.edit(f"Alright!! Successful promoted")


@Client.on_message(filters.command("demote") & filters.group)
async def demote(client, message):
     global new_admin
     if not message.reply_to_message:
         return await message.reply("use this command reply")
     reply = message.reply_to_message
     chat_id = message.chat.id
     new_admin = reply.from_user
     admin = message.from_user
     user_stats = await client.get_chat_member(chat_id, admin.id)
     bot_stats = await client.get_chat_member(chat_id, "self")
     if not bot_stats.privileges:
         return await message.reply("hey dude iam not admin")
     elif not user_stats.privileges:
         return await message.reply("Sorry dude you need admin")
     elif not bot_stats.privileges.can_promote_members:
         return await message.reply("i dont have admin rights ")
     elif not user_stats.privileges.can_promote_members:
         return await message.reply("you need admin rights 😒")
     elif user_stats.privileges.can_promote_members:
          msg = await message.reply_text("`Proccing...`")
          await client.promote_chat_member(
            chat_id,
            new_admin.id,
            privileges=pyrogram.types.ChatPrivileges(
            can_change_info=False,
            can_invite_users=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_chat=False,
            can_manage_video_chats=False    
))
          await msg.edit(f"Hmm!! demoted 🥺 ")
