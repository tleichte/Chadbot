import json
from discord import *
from discord.ext.commands import *
from datetime import *
from utils import utils

try:
    with open("configs/delete.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    print(e)
    print("Failed to load delete cog! Config not found!")
    exit(-1)


class DeleteCog(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_reaction_add(self, added_reaction: Reaction, usr):
    
        msg: Message = added_reaction.message

        if type(added_reaction.emoji) is str:
            return

        if added_reaction.emoji.id != config["emoji_id"]:
            return

        print(f"Delete emoji added to message {msg.id} from {msg.author.display_name} (count: {added_reaction.count})")

        if added_reaction.count < config["count"]:
            return

        now = utils.utcnow()
        if msg.created_at < now - timedelta(days = 3):
            return

        print("Reached count! Deleting message.")
        await msg.delete()


async def setup(bot : Bot):
    await bot.add_cog(DeleteCog(bot))

