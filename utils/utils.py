import discord
from discord.utils import MISSING
from discord import Interaction
from typing import Optional, List
from datetime import datetime, timezone

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


def get_embeds_for_message(message: discord.Message, include_message_link:bool = False) -> List[discord.Embed]:
    embeds : List[discord.Embed] = []
    embed_description = message.content

    only_one_image = len([a for a in message.attachments if "image" in a.content_type]) == 1
    single_image_url : str = ""

    for attachment in message.attachments:
        if "video" in attachment.content_type:
            video_name = attachment.url.split("/")[-1]
            embed_description += f"\n[{video_name}]({attachment.url})"
        elif "image" in attachment.content_type:
            if only_one_image:
                single_image_url = attachment.url
            else:
                embed:discord.Embed = discord.Embed(url=message.jump_url)
                embed.set_image(url=attachment.url)
                embeds.append(embed)
    
    main_embed : discord.Embed = discord.Embed(description=embed_description, timestamp=message.created_at, url=message.jump_url)
    main_embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar)
    if only_one_image:
        main_embed.set_image(url=single_image_url)
    if include_message_link:
        main_embed.add_field(name="",value=f"[Original Message]({message.jump_url})")
    embeds.insert(0, main_embed)

    return embeds