from discord import Interaction
from typing import Optional
from datetime import datetime, timezone

async def respond(interaction: Interaction, out_str: str, ephemeral:bool = False, delete_after:Optional[float]=None):
    if interaction.response.is_done():
        await interaction.edit_original_response(content=out_str)
    else:
        await interaction.response.send_message(out_str, ephemeral=ephemeral)
    if (delete_after is not None):
        original_response = await interaction.original_response()
        await original_response.delete(delay=delete_after)

async def respond_error(interaction: Interaction):
    await respond(interaction, "Oops, there was a problem I wasn't expecting, could you message the bot owner for me? :pleading_face:", ephemeral=True)

def get_timestamp(in_date:datetime) -> int:
    return int(in_date.timestamp())

def utcnow() -> datetime:
    return datetime.now(timezone.utc)