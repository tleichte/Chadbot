from discord import *
from discord.ext.commands import *
from datetime import *
import json

try:
    with open("configs/delete.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    print(e)
    print("Failed to load delete cog! Config not found!")
    exit(-1)


class DeleteCog(Cog):
    def __init__(self, init_bot: Bot, emoji_id: int):
        self.bot = init_bot
        self.emoji_id = emoji_id

    @Cog.listener()
    async def on_reaction_add(self, added_reaction: Reaction, usr):
    
        msg: Message = added_reaction.message

        print("Delete cog: reaction added")

        if type(added_reaction.emoji) is str:
            print("--String reaction added")
            return

        if added_reaction.emoji.id != self.emoji_id:
            print(f"--Added reaction isn't delete emoji (added: {added_reaction.emoji.id}, delete: {self.emoji_id})")
            return

        print(f"Delete emoji added to message {msg.id} from {msg.author.display_name} (count: {added_reaction.count})")

        if added_reaction.count < config["count"]:
            return

        now = datetime.utcnow()
        if msg.created_at.replace(tzinfo=now.tzinfo) < now - timedelta(days = 3):
            return

        print("Reached count! Deleting message.")
        await msg.delete()


async def setup(bot : Bot):
    await bot.add_cog(DeleteCog(bot, config["emoji_id"]))

