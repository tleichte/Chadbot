import discord
from discord.utils import MISSING
from discord import Interaction
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum

async def respond(interaction: Interaction, out_str: str, ephemeral:bool = False, delete_after:Optional[float]=None, embed:discord.Embed = MISSING, view:discord.ui.View = MISSING, embeds:List[discord.Embed] = MISSING):

    # Consolidate embed into list here
    if embed is not MISSING:
        if embeds is MISSING or embeds is None:
            embeds = []
        embeds.insert(0, embed)

    if interaction.response.is_done():
        await interaction.edit_original_response(content=out_str, embeds=embeds, view=view)
    else:
        await interaction.response.send_message(content=out_str, ephemeral=ephemeral, view=view, embeds=embeds)
    if (delete_after is not None):
        original_response = await interaction.original_response()
        await original_response.delete(delay=delete_after)

async def respond_error(interaction: Interaction):
    await respond(interaction, "Oops, there was a problem I wasn't expecting, could you message the bot owner for me? :pleading_face:", ephemeral=True)

def get_timestamp(in_date:datetime) -> int:
    return int(in_date.timestamp())

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def get_url_button(label:str, url:str):
    return discord.ui.Button(label=label, style=discord.ButtonStyle.url, url=url)

def get_url_button_for_message(message:discord.Message, label="Original Message") -> discord.ui.Button:
    return get_url_button(label=label, url=message.jump_url)

class URLButtonView(discord.ui.View):
    def __init__(self, label:str, url:str, timeout: Optional[float] = 0):
        super().__init__(timeout=timeout)
        self.add_item(get_url_button(label, url))

def get_view_for_message(message:discord.Message, label="Original Message") -> discord.ui.View:
    return URLButtonView(label, message.jump_url)

def get_view_for_url(label:str, url:str):
    return URLButtonView(label, url)

class AttachmentType(Enum):
    NONE = 0
    IMAGE = 1
    VIDEO = 2

def get_embeds_for_message(message: discord.Message, color: discord.Color = None) -> List[discord.Embed]:
    embeds : List[discord.Embed] = []
    embed_description = message.content

    only_one_image = len([a for a in message.attachments if get_attachment_type(a) == AttachmentType.IMAGE]) == 1
    single_image_url : str = ""

    for attachment in message.attachments:
        attachment_type = get_attachment_type(attachment)
        if attachment_type == AttachmentType.IMAGE:
            if only_one_image:
                single_image_url = attachment.url
            else:
                embed:discord.Embed = discord.Embed(url=message.jump_url)
                embed.set_image(url=attachment.url)
                embeds.append(embed)
        elif attachment_type == AttachmentType.VIDEO:
            video_name = attachment.url.split("/")[-1]
            embed_description += f"\n[{video_name}]({attachment.url})"
    
    main_embed : discord.Embed = discord.Embed(description=embed_description, timestamp=message.created_at, url=message.jump_url)
    if color is not None:
        main_embed.color = color
    main_embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar)
    if only_one_image:
        main_embed.set_image(url=single_image_url)
    embeds.insert(0, main_embed)

    return embeds

def get_attachment_type(attachment:discord.Attachment) -> AttachmentType:
    if attachment.content_type is None:
        # Dirty image checking method, no content type response header present for some dumb reason
        lower = attachment.url.lower()
        if lower.endswith(".png") or lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".gif") or lower.endswith(".webp"):
            return AttachmentType.IMAGE
    elif "image" in attachment.content_type:
        return AttachmentType.IMAGE
    elif "video" in attachment.content_type:
        return AttachmentType.VIDEO
    return AttachmentType.NONE

def log(tag:str, message:str):
    strnow = datetime.now().strftime("%m-%d-%y %H:%M:%S")
    print(f"[{strnow}][{tag}] - {message}")

def remove_prefix(text:str, prefix:str):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text