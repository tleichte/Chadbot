import traceback
from typing import Any, List, Optional, Union
import discord
from discord.ext.commands import Cog, Bot
from discord import app_commands, Interaction, Role, TextChannel, Guild, Message, Member
import json
from utils import utils

try:
    with open("configs/roles.json", 'r') as config_json:
        config = json.load(config_json)
except Exception as e:
    utils.log("ROLES", e)
    utils.log("ROLES", "Failed to load roles cog! Config not found!")
    exit(-1)


delete_time = 15


def get_emoji_name(emoji_obj):
    if type(emoji_obj) is str:
        return emoji_obj
    return emoji_obj.name


class CreateARoleModal(discord.ui.Modal, title="Create a Role"):
    _nameInput = discord.ui.TextInput(label="Role Name", placeholder="Wumpuses", max_length=32)
    _descriptionInput = discord.ui.TextInput(label="Role Description", placeholder="People who like discord")

    def set_callback(self, callback):
        self.callback = callback

    async def on_submit(self, interaction: discord.Interaction):
        name = self._nameInput.value
        description = self._descriptionInput.value

        await self.callback(interaction, name, description)

class RolesCog(Cog):

    def __init__(self, bot: Bot):
        self.bot = bot
        self.saved_roles = {}
        self.saved_messages = {}
        self.saved_votes = {}

        try:
            with open("data/roles/roles.json", 'r') as infile:
                self.saved_roles = json.load(infile)
            with open("data/roles/messages.json", 'r') as infile:
                self.saved_messages = json.load(infile)
            with open("data/roles/votes.json", 'r') as infile:
                self.saved_votes = json.load(infile)
        except Exception as load_exception:
            utils.log("ROLES", "Failed to load roles cog when getting data!")
            utils.log("ROLES", load_exception)
            exit(-1)

        if self.bot.is_ready():
            utils.log("ROLES", "ON READY IN ROLES COG INIT")
            self.bot.loop.create_task(self.async_init())

    async def async_init(self):
        utils.log("ROLES", "Running Async Init for Roles")
        try:
            role_channel: TextChannel = self.bot.get_channel(config["ChannelID"])
            role_guild: Guild = role_channel.guild
        except Exception as role_exception:
            utils.log("ROLES", "Error grabbing role channel!")
            utils.log("ROLES", role_exception)
            return

        utils.log("ROLES", "--Creating roles and adding to saves")
        # Create roles on the server if they don't exist, add to saved messages
        for saved_role in self.saved_roles:
            utils.log("ROLES", f"Checking role {saved_role}")
            if not discord.utils.get(role_guild.roles, name=saved_role):
                utils.log("ROLES", f"--Creating role {saved_role}")
                await role_guild.create_role(name=saved_role, mentionable=True)
            if self.saved_roles[saved_role] is None:
                utils.log("ROLES", f"--Adding role {saved_role} to saves")
                await self.add_role_to_saves(saved_role, "")

        # save files potentially have changed here
        utils.log("ROLES", f"Updating files and messages")
        await self.update_files_and_messages()

        utils.log("ROLES", "Caching role members with roles")
        # Cache members with given roles
        role_members = {}
        for role_member in role_guild.members:
            for member_role in role_member.roles:
                if member_role.name in self.saved_roles:
                    if member_role.name not in role_members:
                        role_members[member_role.name] = []
                    role_members[member_role.name].append(role_member.id)

        cached_members = {}

        utils.log("ROLES", "Looping through saved messages.")
        for message_id in self.saved_messages:

            # noinspection PyBroadException
            try:
                utils.log("ROLES", f"--Grabbing message with id {int(message_id)}...")
                role_message: Message = await role_channel.fetch_message(int(message_id))
                for role_reaction in role_message.reactions:

                    emoji_name = get_emoji_name(role_reaction.emoji)
                    if emoji_name not in self.saved_messages[message_id]:
                        await role_message.clear_reaction(role_reaction.emoji)
                        continue

                    role_name = self.saved_messages[message_id][emoji_name]

                    utils.log("ROLES", "----Grabbing role reaction users...")
                    reaction_users = [ user async for user in role_reaction.users() ]

                    reaction_users_ids = []
                    for reaction_user in reaction_users:
                        if type(reaction_user) is Member:
                            reaction_users_ids.append(reaction_user.id)
                        else:
                            utils.log("ROLES", f"Found non-member reaction (User {reaction_user.name})")
                            await role_reaction.remove(reaction_user)

                    # Remove roles from users who've removed their reaction on a tracked message
                    if role_name in role_members:
                        for role_member_id in role_members[role_name]:
                            # noinspection PyBroadException
                            try:
                                if role_member_id not in reaction_users_ids:
                                    if role_member_id not in cached_members:
                                        utils.log("ROLES", "----Grabbing non-cached role member...")
                                        cached_members[role_member_id] = await role_guild.fetch_member(role_member_id)
                                            
                                    role_member: Member = cached_members[role_member_id]
                                    role_obj = discord.utils.get(role_guild.roles, name=role_name)
                                    await role_member.remove_roles(role_obj)
                            except Exception:
                                utils.log("ROLES", f"Error when removing role from user id {role_member_id}")
                                utils.log("ROLES", f"Exception: {traceback.print_exc()}")
                                continue

                    # Add roles from users who've added a reaction on a tracked message
                    for reaction_user_id in reaction_users_ids:
                        # noinspection PyBroadException
                        try:
                            if reaction_user_id == self.bot.user.id:
                                continue
                            if reaction_user_id not in role_members:
                                if reaction_user_id not in cached_members:
                                    utils.log("ROLES", "----Grabbing non-cached role member...")
                                    cached_members[reaction_user_id] = await role_guild.fetch_member(reaction_user_id)
                                role_member: Member = cached_members[reaction_user_id]
                                role_obj = discord.utils.get(role_guild.roles, name=role_name)
                                await role_member.add_roles(role_obj)
                        except Exception:
                            utils.log("ROLES", f"Error when getting added reaction user id {reaction_user_id}")
                            utils.log("ROLES", f"Exception: {traceback.print_exc()}")
                            continue

            except Exception:
                utils.log("ROLES", f"Error when retrieving message {message_id}")
                utils.log("ROLES", f"Exception: {traceback.print_exc()}")
                continue

        utils.log("ROLES", "Looping through saved votes.")
        votes_to_delete = []
        for vote_role in self.saved_votes:
            # noinspection PyBroadException
            try:
                saved_vote = self.saved_votes[vote_role]
                msg: Message = await role_channel.fetch_message(saved_vote["message_id"])
                for msg_reaction in msg.reactions:
                    emoji_name = get_emoji_name(msg_reaction.emoji)
                    if emoji_name == config["VoteEmoji"]:
                        if msg_reaction.count > config["VoteCount"]:
                            votes_to_delete.append(vote_role)
                            role_guild: Guild = role_channel.guild
                            utils.log("ROLES", f"--Creating role {vote_role}")
                            await role_guild.create_role(name=vote_role, mentionable=True)
                            await msg.delete()
                            await self.add_role_to_saves(vote_role, saved_vote["desc"])
                    else:
                        await msg.clear_reaction(msg_reaction.emoji)
            except Exception:
                utils.log("ROLES", "Error getting vote!")
                utils.log("ROLES", f"Exception: {traceback.print_exc()}")

        if len(votes_to_delete) > 0:
            for vote_to_delete in votes_to_delete:
                self.saved_votes.pop(vote_to_delete)
            await self.update_files_and_messages()

        utils.log("ROLES", "Async init completed!")

    @Cog.listener("on_ready")
    async def on_ready(self):
        utils.log("ROLES", "ON READY IN ROLES COG LISTENER")
        await self.async_init()

    # ROLE COMMANDS

    role_group = app_commands.Group(name="role", description="Commands", guild_only=True)
    
    @role_group.command(description="(Admin) Renames an existing role")
    @app_commands.rename(
        old_role = "old_name",
        new_role = "new_name"
    )
    @app_commands.describe(
        old_role="Name of old role",
        new_role="Name of new role"
    )
    async def rename(self, interaction: Interaction, old_role: str, new_role: str):

        if not await self.bot.is_owner(interaction.user):
            await utils.respond(interaction, ":triumph: You're not the boss of me!", ephemeral=True)
            return

        if old_role not in self.saved_roles:
            await utils.respond(interaction, f"No role with the name **{old_role}** exists!", ephemeral=True)
            return

        role_obj: Role = discord.utils.get(interaction.guild.roles, name=old_role)
        await role_obj.edit(name=new_role)

        prev_value = self.saved_roles[old_role]
        self.saved_roles.pop(old_role)
        self.saved_roles[new_role] = prev_value

        # Rename in saved messages
        for message_id in self.saved_messages:
            found_message: bool = False
            for num_emoji in config["Emojis"]:
                if num_emoji in self.saved_messages[message_id] and self.saved_messages[message_id][num_emoji] == old_role:
                    self.saved_messages[message_id][num_emoji] = new_role
                    found_message = True
                    break
            if found_message:
                break

        if found_message:
            await interaction.response.defer()
            await self.update_files_and_messages()
            await utils.respond(interaction, f"Renamed role **{old_role}** to **{new_role}**!", delete_after=delete_time)
        else:
            await utils.respond_error(interaction)


    @role_group.command(description="(Admin) Sets the description of an existing role")
    @app_commands.rename(
        role_str = "role",
        new_desc = "new_description"
    )
    @app_commands.describe(
        role_str="Name of role to adjust",
        new_desc="New description for the role"
    )
    async def set_description(self, interaction: Interaction, role_str: str, new_desc: str):
        if not await self.bot.is_owner(interaction.user):
            await utils.respond(interaction, ":triumph: You're not the boss of me!", ephemeral=True)
            return

        if role_str not in self.saved_roles:
            await utils.respond(interaction, f"No role with the name **{role_str}** exists!", ephemeral=True)
            return

        self.saved_roles[role_str]["desc"] = new_desc
        await interaction.response.defer()
        await self.update_files_and_messages()
        await utils.respond(interaction, f"Set description of role **{role_str}** to \"{new_desc}!\"", delete_after=delete_time)


    @role_group.command(description="(Admin) Removes a role")
    @app_commands.rename(
        role_str = "role"
    )
    @app_commands.describe(
        role_str="Name of role to remove"
    )
    async def remove(self, interaction: Interaction, role_str: str):
        if not await self.bot.is_owner(interaction.user):
            await utils.respond(interaction, "You're not the boss of me!", ephemeral=True)
            return

        if role_str not in self.saved_roles:
            await utils.respond(interaction, f"No role with the name **{role_str}** exists!", ephemeral=True)
            return

        role_obj: Role = discord.utils.get(interaction.guild.roles, name=role_str)
        await role_obj.delete()

        # Remove from saved roles
        self.saved_roles.pop(role_str)

        # Remove from saved messages
        found_message: bool = False
        for message_id in self.saved_messages:
            for num_emoji in config["Emojis"]:
                if num_emoji in self.saved_messages[message_id] and self.saved_messages[message_id][num_emoji] == role_str:
                    self.saved_messages[message_id].pop(num_emoji)
                    found_message = True
                    break
            if found_message:
                break

        if found_message:
            await interaction.response.defer()
            await self.update_files_and_messages()
            await utils.respond(interaction, f"Removed role **{role_str}**!", delete_after=delete_time)
        else:
            await utils.respond_error(interaction)


    @role_group.command(description="Brings up the Create a Role modal. Users will vote on whether to add the new role.")
    async def add(self, interaction:discord.Interaction):
       modal = CreateARoleModal()
       modal.set_callback(self.inner_add_role)
       await interaction.response.send_modal(modal)

    async def inner_add_role(self, interaction: Interaction, role_str: str, role_desc: str):
        if role_str in self.saved_roles:
            await utils.respond(interaction, f"A role with the name **{role_str}** already exists!", ephemeral=True)
            return

        if role_str in self.saved_votes:
            await utils.respond(interaction, f"A role with the name **{role_str}** is already being voted on!", ephemeral=True)
            return

        if discord.utils.get(interaction.guild.roles, name=role_str):
            await utils.respond(interaction, f"The name **{role_str}** is already reserved for this server!", ephemeral=True)
            return


        try:
            role_channel: TextChannel = self.bot.get_channel(config["ChannelID"])
        except Exception as role_exception:
            await utils.respond_error(interaction)
            utils.log("ROLES", "Error grabbing role channel!")
            utils.log("ROLES", role_exception)
            return
        
        await interaction.response.defer()

        vote_str = f":ballot_box: Voting on new role **{role_str}** ({role_desc}).\n" \
                   f"This vote was initiated by {interaction.user.mention}.\n" \
                   f"React with {config['VoteEmoji']} if you want this role added!\n" \
                   f"It will be added if {config['VoteCount']} people want it. _Not including my reaction of course :)_"
        vote_message: Message = await role_channel.send(vote_str)
        await vote_message.add_reaction(config["VoteEmoji"])

        saved_obj = {"user": interaction.user.id, "message_id": vote_message.id, "desc": role_desc}

        self.saved_votes[role_str] = saved_obj
        await self.update_files_and_messages()
        await utils.respond(interaction, f"You started a vote for **{role_str}** in {role_channel.mention}!")


    # noinspection PyBroadException
    @role_group.command(description="Cancels a vote (if you started vote or are admin)")
    @app_commands.rename(
        role_str = "role"
    )
    @app_commands.describe(
        role_str="Name of role to cancel vote"
    )
    async def cancel(self, interaction: Interaction, role_str: str):
        utils.log("ROLES", f"Cancel command from {interaction.user.display_name}")
        
        if role_str not in self.saved_votes:
            await utils.respond(interaction, f"No vote exists for the role **{role_str}**!", ephemeral=True)
            return

        try:
            role_channel: TextChannel = self.bot.get_channel(config["ChannelID"])
        except Exception:
            utils.log("ROLES", "Error grabbing role channel!")
            traceback.print_exc()
            return

        if interaction.user.id != self.saved_votes[role_str]["user"] and not await self.bot.is_owner(interaction.user):
            await utils.respond(interaction, ":triumph: You didn't start that vote and you're not the boss of me, so you can't cancel it.", ephemeral=True)
            return

        try:
            msg: Message = await role_channel.fetch_message(self.saved_votes[role_str]["message_id"])
            await msg.delete()
        except Exception:
            await utils.respond_error(interaction)
            utils.log("ROLES", "Error grabbing message!")
            traceback.print_exc()
            return

        await interaction.response.defer()

        self.saved_votes.pop(role_str)

        await self.update_files_and_messages()
        await utils.respond(interaction, f"Cancelled the vote for **{role_str}**.")

    @role_group.command(description="Shows help dialog")
    async def help(self, interaction: Interaction):
        with open("help/roles.json", 'r') as help_json:
            help_obj = json.load(help_json)

        help_embed: discord.Embed = discord.Embed()

        color_obj = help_obj["color"]
        help_embed.colour = discord.Color.from_rgb(color_obj["r"], color_obj["g"], color_obj["b"])

        author_obj = help_obj["author"]
        help_embed.set_author(name=author_obj["name"], icon_url=author_obj["icon_url"], url=author_obj["url"])

        help_embed.title = help_obj["title"]
        help_embed.description = help_obj["description"]

        for command in self.walk_app_commands():
            if not isinstance(command, app_commands.Group):
                help_embed.add_field(name="/" + command.qualified_name, value=command.description, inline=False)

        await interaction.response.send_message(embed=help_embed)

    # LISTENERS

    @Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        utils.log("ROLES", "Raw reaction added!")

        # utils.log("ROLES", f"Channel id: {payload.channel_id}, Config: {config['ChannelID']}")
        if payload.channel_id != config["ChannelID"]:
            utils.log("ROLES", "--Not equal, returning")
            return

        role_member: Member = payload.member
        if self.bot.user.id == role_member.id:
            utils.log("ROLES", "--It was me!")
            return

        role_channel: TextChannel = self.bot.get_channel(payload.channel_id)
        msg: Message = await role_channel.fetch_message(payload.message_id)

        for vote_role in self.saved_votes:
            if msg.id == self.saved_votes[vote_role]["message_id"]:
                emoji_name = get_emoji_name(payload.emoji)
                if emoji_name == config["VoteEmoji"]:
                    utils.log("ROLES", "--Reaction was the vote!")
                    for msg_reaction in msg.reactions:
                        msg_reaction_name = get_emoji_name(msg_reaction.emoji)
                        utils.log("ROLES", f"----Msg Reaction Name: {msg_reaction_name}, emoji_name: {emoji_name}")
                        if msg_reaction_name == emoji_name:
                            utils.log("ROLES", f"----Reaction count: {msg_reaction.count}")
                            if msg_reaction.count > config["VoteCount"]:  # > since the bots reaction is there too
                                role_desc = self.saved_votes[vote_role]["desc"]
                                self.saved_votes.pop(vote_role)
                                role_guild: Guild = role_channel.guild
                                await role_guild.create_role(name=vote_role, mentionable=True)
                                await msg.delete()
                                await self.add_role_to_saves(vote_role, role_desc)
                                await self.update_files_and_messages()

                                out_msg: Message = await role_channel.fetch_message(self.saved_roles[vote_role]["message_id"])
                                await out_msg.channel.send(f"Added the new role **{vote_role}** here!\n{out_msg.jump_url}", delete_after=delete_time)
                            break
                else:
                    utils.log("ROLES", "--Wrong reaction...")
                    await msg.clear_reaction(payload.emoji)
                return

        for message_id in self.saved_messages:
            if int(message_id) == msg.id:
                emoji_name = get_emoji_name(payload.emoji)
                if emoji_name in self.saved_messages[message_id]:
                    role_obj = discord.utils.get(role_channel.guild.roles,
                                                 name=self.saved_messages[message_id][emoji_name])
                    await role_member.add_roles(role_obj)
                    return

        await msg.clear_reaction(payload.emoji)

    @Cog.listener("on_raw_reaction_remove")
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        utils.log("ROLES", "Reaction removed!")

        if payload.channel_id != config["ChannelID"]:
            utils.log("ROLES", "--Wrong channel")
            return

        await self.bot.wait_until_ready()

        role_channel: TextChannel = self.bot.get_channel(payload.channel_id)

        utils.log("ROLES", "--Finding roles")
        for saved_message_id in self.saved_messages:
            if int(saved_message_id) == payload.message_id:
                emoji_name = get_emoji_name(payload.emoji)
                if emoji_name in self.saved_messages[saved_message_id]:
                    utils.log("ROLES", "--Found emoji in saved message")
                    role_obj: Role = discord.utils.get(role_channel.guild.roles,
                                                       name=self.saved_messages[saved_message_id][emoji_name])
                    
                    # noinspection PyBroadException
                    try:
                        role_member: Member = await role_channel.guild.fetch_member(payload.user_id)
                    except Exception:
                        utils.log("ROLES", "Error when getting role member!")
                        traceback.print_exc()
                        return
                    
                    await role_member.remove_roles(role_obj)
                return

    # noinspection PyBroadException
    @Cog.listener("on_member_remove")
    async def on_member_remove(self, left_member: Member):

        utils.log("ROLES", f"User {left_member.display_name} left; updating messages")
        role_channel: TextChannel = self.bot.get_channel(config["ChannelID"])

        for message_id in self.saved_messages:
            try:
                msg: Message = await role_channel.fetch_message(int(message_id))
                for msg_reaction in msg.reactions:
                    try:
                        await msg.remove_reaction(msg_reaction.emoji, left_member)
                    except Exception:
                        utils.log("ROLES", "Exception while removing reaction from leaving user")
                        utils.log("ROLES", f"Exception: {traceback.print_exc()}")
            except Exception:
                utils.log("ROLES", f"Exception while getting message with id {message_id}")
                utils.log("ROLES", f"Exception: {traceback.print_exc()}")

    # HELPERS

    async def add_role_to_saves(self, role_str: str, role_desc: str):

        # Add to current messages if a slot is available
        for message_id in self.saved_messages:
            for role_emoji in config["Emojis"]:
                if role_emoji not in self.saved_messages[message_id]:
                    self.saved_roles[role_str] = {"message_id": int(message_id), "desc": role_desc}
                    self.saved_messages[message_id][role_emoji] = role_str
                    return
        # Send new message and set values accordingly
        role_channel: TextChannel = self.bot.get_channel(config["ChannelID"])
        new_message: Message = await role_channel.send("Generating new message...")
        self.saved_roles[role_str] = {"message_id": new_message.id, "desc": role_desc}
        self.saved_messages[str(new_message.id)] = {}
        self.saved_messages[str(str(new_message.id))][config["Emojis"][0]] = role_str

    async def update_files_and_messages(self):

        #TODO utilize versioning to prevent as many API calls

        utils.log("ROLES", "Updating messages...")
        role_channel: TextChannel = self.bot.get_channel(config["ChannelID"])

        messages_to_delete = []
        for message_id in self.saved_messages:
            try:
                msg: Message = await role_channel.fetch_message(int(message_id))
                if len(self.saved_messages[message_id]) == 0:
                    messages_to_delete.append(message_id)
                    await msg.delete()
                    continue

                new_str = "React to self-assign one of the roles!"
                for emoji_name in self.saved_messages[message_id]:
                    role_name = self.saved_messages[message_id][emoji_name]
                    role_desc = self.saved_roles[role_name]["desc"]
                    new_str += f"\n{emoji_name} - **{role_name}** ({role_desc})"
                    has_emoji = False
                    for msg_reaction in msg.reactions:
                        if get_emoji_name(msg_reaction.emoji) == emoji_name:
                            has_emoji = True
                            break
                    if not has_emoji:
                        utils.log("ROLES", f"Attempting to add emoji_id {emoji_name}")
                        await msg.add_reaction(emoji_name)
                await msg.edit(content=new_str)

                for msg_reaction in msg.reactions:
                    if get_emoji_name(msg_reaction.emoji) not in self.saved_messages[message_id]:
                        await msg.clear_reaction(msg_reaction.emoji)

            except Exception as update_exception:
                utils.log("ROLES", f"Error getting message ID {message_id}")
                utils.log("ROLES", update_exception)

        for message_to_delete in messages_to_delete:
            self.saved_messages.pop(message_to_delete)

        utils.log("ROLES", "Updating files...")
        with open("data/roles/roles.json", 'w') as outfile:
            json.dump(self.saved_roles, outfile)
        with open("data/roles/messages.json", 'w') as outfile:
            json.dump(self.saved_messages, outfile)
        with open("data/roles/votes.json", 'w') as outfile:
            json.dump(self.saved_votes, outfile)

async def setup(bot : Bot):
    await bot.add_cog(RolesCog(bot))
