import discord
import traceback
import asyncio
from discord import Intents, app_commands
from discord.ext import commands
from discord.ext.commands import Bot, Context, Command, CommandError
import json
import logging

# OPEN INITIAL FILES
try:
    with open("configs/main.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    print(e)
    print("Config not found!")
    exit(-1)


class MyBot(Bot):
    async def setup_hook(self):
        cogs = [
            "delete",
            "roles"
        ]

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

async def respond(ctx: Context, message: str):
    await ctx.send(f"{ctx.author.mention}\n{message}")

async def respond_generic_error(ctx:Context):
    await respond(ctx, f":grey_question: Sorry, I didn't recognize that. Check *help* to see what I do know.", False)

@bot.hybrid_command(description="(Admin) Shuts down the bot")
async def bedtime(ctx: Context):
    if await bot.is_owner(ctx.author):
        print("Owner verified, shutting down")
        await ctx.send(":yawning_face: :sleeping:")
        await bot.close()
        print("Shutdown complete")
    else:
        print("User doesn't have kill permission.")
        await ctx.send(":triumph: You're not the boss of me.")


@bot.hybrid_command(description="Shows the bot's ping")
async def ping(ctx: Context):
    await ctx.send(f":ping_pong: Pong! ({round(bot.latency*1000)}ms)")


@bot.event
async def on_command_error(ctx:Context, error:CommandError):

    cmd: Command = ctx.command

    if cmd is None:
        print("Unrecognized command detected; ignoring")
        return

    print(f"Command error! Message: \"{ctx.message.content}\", Error type: {type(error)}")
    if isinstance(error, (commands.BadArgument, commands.CommandNotFound, commands.MissingRequiredArgument)):
        await respond_generic_error(ctx)
    else:
        traceback.print_exception(type(error),error,error.__traceback__)
        await respond(ctx, f"Sorry, something went wrong... I feel like I have butterflies... no, bugs, in my stomach. :sick:", False)


@bot.hybrid_command(description="(Admin) Refreshes a cog.")
@app_commands.rename(cog_str="cog_name")
@app_commands.describe(cog_str="Name of cog to refresh")
async def refresh_cog(ctx: Context, cog_str: str):
    if await bot.is_owner(ctx.author):
        try:
            print(f"Owner verified, refreshing cog {cog_str}")
            await bot.reload_extension(f"cogs.{cog_str}")
            await bot.tree.sync()
            await ctx.send(f"Refreshed cog {cog_str}!")
        except Exception as refresh_e:
            print(f"Failed to refresh cog {cog_str}!")
            print(refresh_e)
    else:
        await ctx.send(f"{ctx.author.mention} :triumph: You're not the boss of me!")
        print("Someone not the bot owner tried to refresh!")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} - {bot.user.id}")

if __name__ == "__main__":
    bot.run(config["token"])