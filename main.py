import importlib
import traceback
from discord import Intents, app_commands, Interaction
from discord.ext import commands
from discord.ext.commands import Bot, Command, CommandError
import json
from utils import utils, db

# OPEN INITIAL FILES
try:
    with open("configs/main.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    print(e)
    print("Config not found!")
    exit(-1)

try:
    with open("configs/token.json", 'r') as token_json:
        token_config = json.load(token_json)
except Exception as e:
    print(e)
    print("Token config not found!")
    exit(-1)


class MyBot(Bot):
    async def setup_hook(self):
        cogs = config["cogs"]

        async for guild in self.fetch_guilds():
            app_commands = await self.tree.fetch_commands(guild=guild)
            for app_command in app_commands:
                await app_command.delete()

        for cog in cogs:
            cog_to_load = f"cogs.{cog}"
            print(f"Loading cog {cog_to_load}")
            await self.load_extension(cog_to_load)
        
        await self.tree.sync()

intents = Intents.default()
intents.members = True
intents.message_content = True
bot = MyBot(command_prefix="!", intents=intents)
bot.remove_command('help')

@bot.tree.command(description="(Admin) Shuts down the bot")
async def bedtime(interaction: Interaction):
    if await bot.is_owner(interaction.user):
        print("Owner verified, shutting down")
        await utils.respond(interaction, ":yawning_face: :sleeping:", ephemeral=True)
        await bot.close()
        print("Shutdown complete")
    else:
        print("User doesn't have kill permission.")
        await utils.respond(interaction, ":triumph: You're not the boss of me.", ephemeral=True)


@bot.tree.command(description="Shows the bot's ping")
async def ping(interaction: Interaction):
    await utils.respond(interaction, f":ping_pong: Pong! ({round(bot.latency*1000)}ms)")

@bot.tree.command(description="(Admin) Refreshes a cog if loaded. If a cog exists but is unloaded, it is loaded.")
@app_commands.rename(cog_str="cog_name")
@app_commands.describe(cog_str="Name of cog to refresh", refresh_tree="Whether or not to re-sync command tree when a loaded cog is refreshed (new cogs automatically refresh tree)")
async def refresh_cog(interaction: Interaction, cog_str: str, refresh_tree: bool = False):
    if await bot.is_owner(interaction.user):
        await interaction.response.defer(ephemeral=True)
        print(f"Owner verified, refreshing cog {cog_str}")

        full_cog_str = f"cogs.{cog_str}"

        # When refreshing cog, make sure latest utils functions are usable
        importlib.reload(utils)
        importlib.reload(db)
        
        try:
            new_cog = full_cog_str not in bot.extensions.keys()
            if new_cog:
                await bot.load_extension(full_cog_str)
            else:
                await bot.reload_extension(full_cog_str)
            if refresh_tree or new_cog:
                print("Syncing app command tree...")
                await bot.tree.sync()
                print(f"App command tree synced")

            print(f"Cog {cog_str} refreshed")
            
            await utils.respond(interaction, f"Successfully refreshed cog **{cog_str}**!", ephemeral=True)

        except commands.errors.ExtensionNotFound:
            print(f"Given cog {cog_str} doesn't exist.")
            out_message = f"Cog **{cog_str}** doesn't exist! Available cogs:\n"
            for full_extension_name in bot.extensions.keys():
                out_message += f"- {utils.remove_prefix(full_extension_name, 'cogs.')}\n"
            await utils.respond(interaction, out_message, ephemeral=True)

        except Exception:
            print(f"Failed to refresh cog {cog_str}!")
            traceback.print_exc()
            await utils.respond(interaction, f"Error refreshing cog **{cog_str}**! Check the output for exception details.", ephemeral=True)

    else:
        await utils.respond(interaction, ":triumph: You're not the boss of me!", ephemeral=True)
        print("Someone not the bot owner tried to refresh!")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} - {bot.user.id}")

if __name__ == "__main__":
    bot.run(token_config["token"])