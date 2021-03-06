import discord
from discord.ext import commands
from .utils.dataIO import fileIO, dataIO
from .utils import checks
from __main__ import send_cmd_help, settings
from collections import deque
from cogs.utils.chat_formatting import escape_mass_mentions
import os
import logging
import asyncio


class Mod:
    """Moderation tools."""

    def __init__(self, bot):
        self.bot = bot
        self.whitelist_list = dataIO.load_json("data/mod/whitelist.json")
        self.blacklist_list = dataIO.load_json("data/mod/blacklist.json")
        self.ignore_list = dataIO.load_json("data/mod/ignorelist.json")
        self.filter = dataIO.load_json("data/mod/filter.json")
        self.past_names = dataIO.load_json("data/mod/past_names.json")
        self.past_nicknames = dataIO.load_json("data/mod/past_nicknames.json")

    @commands.group(pass_context=True, no_pm=True)
    @checks.serverowner_or_permissions(administrator=True)
    async def modset(self, ctx):
        """Manages server administration settings."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            msg = "```"
            for k, v in settings.get_server(ctx.message.server).items():
                msg += str(k) + ": " + str(v) + "\n"
            msg += "```"
            await self.bot.say(msg)

    @modset.command(name="adminrole", pass_context=True, no_pm=True)
    async def _modset_adminrole(self, ctx, role_name: str):
        """Sets the admin role for this server, case insensitive."""
        server = ctx.message.server
        if server.id not in settings.servers:
            await self.bot.say("Remember to set modrole too.")
        settings.set_server_admin(server, role_name)
        await self.bot.say("Admin role set to '{}'".format(role_name))

    @modset.command(name="modrole", pass_context=True, no_pm=True)
    async def _modset_modrole(self, ctx, role_name: str):
        """Sets the mod role for this server, case insensitive."""
        server = ctx.message.server
        if server.id not in settings.servers:
            await self.bot.say("Remember to set adminrole too.")
        settings.set_server_mod(server, role_name)
        await self.bot.say("Mod role set to '{}'".format(role_name))

    @commands.command(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(kick_members=True)
    async def kick(self, ctx, user: discord.Member):
        """Kicks user."""
        author = ctx.message.author
        try:
            await self.bot.kick(user)
            logger.info("{}({}) kicked {}({})".format(
                author.name, author.id, user.name, user.id))
            await self.bot.say("Done. That felt good.")
        except discord.errors.Forbidden:
            await self.bot.say("I'm not allowed to do that.")
        except Exception as e:
            print(e)

    @commands.command(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(ban_members=True)
    async def ban(self, ctx, user: discord.Member, days: int=0):
        """Bans user and deletes last X days worth of messages.

        Minimum 0 days, maximum 7. Defaults to 0."""
        author = ctx.message.author
        if days < 0 or days > 7:
            await self.bot.say("Invalid days. Must be between 0 and 7.")
            return
        try:
            await self.bot.ban(user, days)
            logger.info("{}({}) banned {}({}), deleting {} days worth of messages".format(
                author.name, author.id, user.name, user.id, str(days)))
            await self.bot.say("Done. It was about time.")
        except discord.errors.Forbidden:
            await self.bot.say("I'm not allowed to do that.")
        except Exception as e:
            print(e)

    @commands.command(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(ban_members=True)
    async def softban(self, ctx, user: discord.Member):
        """Kicks the user, deleting 1 day worth of messages."""
        server = ctx.message.server
        channel = ctx.message.channel
        can_ban = channel.permissions_for(server.me).ban_members
        author = ctx.message.author
        if can_ban:
            try:
                try: # We don't want blocked DMs preventing us from banning
                    msg = await self.bot.send_message(user, "You have been banned and "
                              "then unbanned as a quick way to delete your messages.\n"
                              "You can now join the server again.")
                except:
                    pass
                await self.bot.ban(user, 1)
                logger.info("{}({}) softbanned {}({}), deleting 1 day worth "
                    "of messages".format(author.name, author.id, user.name,
                     user.id))
                await self.bot.unban(server, user)
                await self.bot.say("Done. Enough chaos.")
            except discord.errors.Forbidden:
                await self.bot.say("My role is not high enough to softban that user.")
                await self.bot.delete_message(msg)
            except Exception as e:
                print(e)
        else:
            await self.bot.say("I'm not allowed to do that.")

    @commands.command(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(manage_nicknames=True)
    async def rename(self, ctx, user : discord.Member, *, nickname=""):
        """Changes user's nickname

        Leaving the nickname empty will remove it."""
        nickname = nickname.strip()
        if nickname == "":
            nickname = None
        try:
            await self.bot.change_nickname(user, nickname)
            await self.bot.say("Done.")
        except discord.Forbidden:
            await self.bot.say("I cannot do that, I lack the "
                "\"Manage Nicknames\" permission.")

    @commands.group(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def cleanup(self, ctx):
        """Deletes messages.

        cleanup messages [number]
        cleanup user [name/mention] [number]
        cleanup text \"Text here\" [number]"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @cleanup.command(pass_context=True, no_pm=True)
    async def text(self, ctx, text: str, number: int):
        """Deletes last X messages matching the specified text.

        Example:
        cleanup text \"test\" 5

        Remember to use double quotes."""
        if number < 1:
            number = 1
        author = ctx.message.author
        message = ctx.message
        channel = ctx.message.channel
        logger.info("{}({}) deleted {} messages containing '{}' in channel {}".format(author.name,
            author.id, str(number), text, message.channel.name))
        if self.bot.user.bot and self.discordpy_updated():
            def to_delete(m):
                if m == ctx.message or text in m.content:
                    return True
                else:
                    return False
            try:
                await self.bot.purge_from(channel, limit=number+1, check=to_delete)
            except discord.errors.Forbidden:
                await self.bot.say("I need permissions to manage messages "
                                   "in this channel.")
        else:
            await self.legacy_cleanup_text_messages(ctx, text, number)


    async def legacy_cleanup_text_messages(self, ctx, text, number):
        message = ctx.message
        cmdmsg = ctx.message
        if self.bot.user.bot:
            print("Your discord.py is outdated, defaulting to slow deletion.")
        try:
            if number > 0 and number < 10000:
                while True:
                    new = False
                    async for x in self.bot.logs_from(message.channel, limit=100, before=message):
                        if number == 0:
                            await self._delete_message(cmdmsg)
                            await asyncio.sleep(0.25)
                            return
                        if text in x.content:
                            await self._delete_message(x)
                            await asyncio.sleep(0.25)
                            number -= 1
                        new = True
                        message = x
                    if not new or number == 0:
                        await self._delete_message(cmdmsg)
                        await asyncio.sleep(0.25)
                        break
        except discord.errors.Forbidden:
            await self.bot.send_message(message.channel, "I need permissions"
                 " to manage messages in this channel.")

    @cleanup.command(pass_context=True, no_pm=True)
    async def user(self, ctx, user: discord.Member, number: int):
        """Deletes last X messages from specified user.

        Examples:
        cleanup user @\u200bTwentysix 2
        cleanup user Red 6"""
        if number < 1:
            number = 1
        author = ctx.message.author
        channel = ctx.message.channel
        message = ctx.message
        logger.info("{}({}) deleted {} messages made by {}({}) in channel {}".format(author.name,
            author.id, str(number), user.name, user.id, message.channel.name))
        if self.bot.user.bot and self.discordpy_updated():
            def is_user(m):
                if m == ctx.message or m.author == user:
                    return True
                else:
                    return False
            try:
                await self.bot.purge_from(channel, limit=number+1, check=is_user)
            except discord.errors.Forbidden:
                await self.bot.say("I need permissions to manage messages "
                                   "in this channel.")
        else:
            await self.legacy_cleanup_user_messages(ctx, user, number)

    @cleanup.command(pass_context=True, no_pm=True)
    async def after(self, ctx, message_id : int):
        """Deletes all messages after specified message

        To get a message id, enable developer mode in Discord's
        settings, 'appearance' tab. Then right click a message
        and copy its id.
        """
        channel = ctx.message.channel
        try:
            message = await self.bot.get_message(channel, str(message_id))
        except discord.errors.NotFound:
            await self.bot.say("Message not found.")
            return
        except discord.errors.Forbidden:
            if self.bot.user.bot:
                await self.bot.say("I'm not authorized to get that message.")
            else:
                await self.bot.say("This function is limited to bot accounts.")
            return
        except discord.errors.HTTPException:
            await self.bot.say("Couldn't retrieve the message.")
            return

        try:
            await self.bot.purge_from(channel, limit=2500, after=message)
        except discord.errors.Forbidden:
                await self.bot.say("I need permissions to manage messages "
                                   "in this channel.")

    async def legacy_cleanup_user_messages(self, ctx, user, number):
        author = ctx.message.author
        message = ctx.message
        cmdmsg = ctx.message
        if self.bot.user.bot:
            print("Your discord.py is outdated, defaulting to slow deletion.")
        try:
            if number > 0 and number < 10000:
                while True:
                    new = False
                    async for x in self.bot.logs_from(message.channel, limit=100, before=message):
                        if number == 0:
                            await self._delete_message(cmdmsg)
                            await asyncio.sleep(0.25)
                            return
                        if x.author.id == user.id:
                            await self._delete_message(x)
                            await asyncio.sleep(0.25)
                            number -= 1
                        new = True
                        message = x
                    if not new or number == 0:
                        await self._delete_message(cmdmsg)
                        await asyncio.sleep(0.25)
                        break
        except discord.errors.Forbidden:
            await self.bot.send_message(ctx.channel, "I need permissions "
                            "to manage messages in this channel.")


    @cleanup.command(pass_context=True, no_pm=True)
    async def messages(self, ctx, number: int):
        """Deletes last X messages.

        Example:
        cleanup messages 26"""
        if number < 1:
            number = 1
        author = ctx.message.author
        channel = ctx.message.channel
        logger.info("{}({}) deleted {} messages in channel {}".format(author.name,
            author.id, str(number), channel.name))
        if self.bot.user.bot and self.discordpy_updated():
            try:
                await self.bot.purge_from(channel, limit=number+1)
            except discord.errors.Forbidden:
                await self.bot.say("I need permissions to manage messages in this channel.")
        else:
            await self.legacy_cleanup_messages(ctx, number)

    async def legacy_cleanup_messages(self, ctx, number):
        author = ctx.message.author
        channel = ctx.message.channel
        if self.bot.user.bot:
                print("Your discord.py is outdated, defaulting to slow deletion.")
        try:
            if number > 0 and number < 10000:
                async for x in self.bot.logs_from(channel, limit=number + 1):
                    await self._delete_message(x)
                    await asyncio.sleep(0.25)
        except discord.errors.Forbidden:
            await self.bot.send_message(channel, "I need permissions to manage messages in this channel.")

    @commands.group(pass_context=True)
    @checks.is_owner()
    async def blacklist(self, ctx):
        """Bans user from using the bot"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @blacklist.command(name="add")
    async def _blacklist_add(self, user: discord.Member):
        """Adds user to bot's blacklist"""
        if user.id not in self.blacklist_list:
            self.blacklist_list.append(user.id)
            fileIO("data/mod/blacklist.json", "save", self.blacklist_list)
            await self.bot.say("User has been added to blacklist.")
        else:
            await self.bot.say("User is already blacklisted.")

    @blacklist.command(name="remove")
    async def _blacklist_remove(self, user: discord.Member):
        """Removes user to bot's blacklist"""
        if user.id in self.blacklist_list:
            self.blacklist_list.remove(user.id)
            fileIO("data/mod/blacklist.json", "save", self.blacklist_list)
            await self.bot.say("User has been removed from blacklist.")
        else:
            await self.bot.say("User is not in blacklist.")

    @commands.group(pass_context=True)
    @checks.is_owner()
    async def whitelist(self, ctx):
        """Users who will be able to use the bot"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @whitelist.command(name="add")
    async def _whitelist_add(self, user: discord.Member):
        """Adds user to bot's whitelist"""
        if user.id not in self.whitelist_list:
            if not self.whitelist_list:
                msg = "\nAll users not in whitelist will be ignored (owner, admins and mods excluded)"
            else:
                msg = ""
            self.whitelist_list.append(user.id)
            fileIO("data/mod/whitelist.json", "save", self.whitelist_list)
            await self.bot.say("User has been added to whitelist." + msg)
        else:
            await self.bot.say("User is already whitelisted.")

    @whitelist.command(name="remove")
    async def _whitelist_remove(self, user: discord.Member):
        """Removes user to bot's whitelist"""
        if user.id in self.whitelist_list:
            self.whitelist_list.remove(user.id)
            fileIO("data/mod/whitelist.json", "save", self.whitelist_list)
            await self.bot.say("User has been removed from whitelist.")
        else:
            await self.bot.say("User is not in whitelist.")

    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_channels=True)
    async def ignore(self, ctx):
        """Adds servers/channels to ignorelist"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            await self.bot.say(self.count_ignored())

    @ignore.command(name="channel", pass_context=True)
    async def ignore_channel(self, ctx, channel: discord.Channel=None):
        """Ignores channel

        Defaults to current one"""
        current_ch = ctx.message.channel
        if not channel:
            if current_ch.id not in self.ignore_list["CHANNELS"]:
                self.ignore_list["CHANNELS"].append(current_ch.id)
                fileIO("data/mod/ignorelist.json", "save", self.ignore_list)
                await self.bot.say("Channel added to ignore list.")
            else:
                await self.bot.say("Channel already in ignore list.")
        else:
            if channel.id not in self.ignore_list["CHANNELS"]:
                self.ignore_list["CHANNELS"].append(channel.id)
                fileIO("data/mod/ignorelist.json", "save", self.ignore_list)
                await self.bot.say("Channel added to ignore list.")
            else:
                await self.bot.say("Channel already in ignore list.")

    @ignore.command(name="server", pass_context=True)
    async def ignore_server(self, ctx):
        """Ignores current server"""
        server = ctx.message.server
        if server.id not in self.ignore_list["SERVERS"]:
            self.ignore_list["SERVERS"].append(server.id)
            fileIO("data/mod/ignorelist.json", "save", self.ignore_list)
            await self.bot.say("This server has been added to the ignore list.")
        else:
            await self.bot.say("This server is already being ignored.")

    @commands.group(pass_context=True, no_pm=True)
    @checks.admin_or_permissions(manage_channels=True)
    async def unignore(self, ctx):
        """Removes servers/channels from ignorelist"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            await self.bot.say(self.count_ignored())

    @unignore.command(name="channel", pass_context=True)
    async def unignore_channel(self, ctx, channel: discord.Channel=None):
        """Removes channel from ignore list

        Defaults to current one"""
        current_ch = ctx.message.channel
        if not channel:
            if current_ch.id in self.ignore_list["CHANNELS"]:
                self.ignore_list["CHANNELS"].remove(current_ch.id)
                fileIO("data/mod/ignorelist.json", "save", self.ignore_list)
                await self.bot.say("This channel has been removed from the ignore list.")
            else:
                await self.bot.say("This channel is not in the ignore list.")
        else:
            if channel.id in self.ignore_list["CHANNELS"]:
                self.ignore_list["CHANNELS"].remove(channel.id)
                fileIO("data/mod/ignorelist.json", "save", self.ignore_list)
                await self.bot.say("Channel removed from ignore list.")
            else:
                await self.bot.say("That channel is not in the ignore list.")

    @unignore.command(name="server", pass_context=True)
    async def unignore_server(self, ctx):
        """Removes current server from ignore list"""
        server = ctx.message.server
        if server.id in self.ignore_list["SERVERS"]:
            self.ignore_list["SERVERS"].remove(server.id)
            fileIO("data/mod/ignorelist.json", "save", self.ignore_list)
            await self.bot.say("This server has been removed from the ignore list.")
        else:
            await self.bot.say("This server is not in the ignore list.")

    def count_ignored(self):
        msg = "```Currently ignoring:\n"
        msg += str(len(self.ignore_list["CHANNELS"])) + " channels\n"
        msg += str(len(self.ignore_list["SERVERS"])) + " servers\n```\n"
        return msg

    @commands.group(name="filter", pass_context=True, no_pm=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def _filter(self, ctx):
        """Adds/removes words from filter

        Use double quotes to add/remove sentences
        Using this command with no subcommands will send
        the list of the server's filtered words."""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
            server = ctx.message.server
            author = ctx.message.author
            msg = ""
            if server.id in self.filter.keys():
                if self.filter[server.id] != []:
                    word_list = self.filter[server.id]
                    for w in word_list:
                        msg += '"' + w + '" '
                    await self.bot.send_message(author, "Words filtered in this server: " + msg)

    @_filter.command(name="add", pass_context=True)
    async def filter_add(self, ctx, *words: str):
        """Adds words to the filter

        Use double quotes to add sentences
        Examples:
        filter add word1 word2 word3
        filter add \"This is a sentence\""""
        if words == ():
            await send_cmd_help(ctx)
            return
        server = ctx.message.server
        added = 0
        if server.id not in self.filter.keys():
            self.filter[server.id] = []
        for w in words:
            if w.lower() not in self.filter[server.id] and w != "":
                self.filter[server.id].append(w.lower())
                added += 1
        if added:
            fileIO("data/mod/filter.json", "save", self.filter)
            await self.bot.say("Words added to filter.")
        else:
            await self.bot.say("Words already in the filter.")

    @_filter.command(name="remove", pass_context=True)
    async def filter_remove(self, ctx, *words: str):
        """Remove words from the filter

        Use double quotes to remove sentences
        Examples:
        filter remove word1 word2 word3
        filter remove \"This is a sentence\""""
        if words == ():
            await send_cmd_help(ctx)
            return
        server = ctx.message.server
        removed = 0
        if server.id not in self.filter.keys():
            await self.bot.say("There are no filtered words in this server.")
            return
        for w in words:
            if w.lower() in self.filter[server.id]:
                self.filter[server.id].remove(w.lower())
                removed += 1
        if removed:
            fileIO("data/mod/filter.json", "save", self.filter)
            await self.bot.say("Words removed from filter.")
        else:
            await self.bot.say("Those words weren't in the filter.")

    @commands.group(no_pm=True, pass_context=True)
    @checks.admin_or_permissions(manage_roles=True)
    async def editrole(self, ctx):
        """Edits roles settings"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @editrole.command(aliases=["color"], pass_context=True)
    async def colour(self, ctx, role: discord.Role, value: discord.Colour):
        """Edits a role's colour

        Use double quotes if the role contains spaces.
        Colour must be in hexadecimal format.
        \"http://www.w3schools.com/colors/colors_picker.asp\"
        Examples:
        !editrole colour \"The Transistor\" #ff0000
        !editrole colour Test #ff9900"""
        author = ctx.message.author
        try:
            await self.bot.edit_role(ctx.message.server, role, color=value)
            logger.info("{}({}) changed the colour of role '{}'".format(
                author.name, author.id, role.name))
            await self.bot.say("Done.")
        except discord.Forbidden:
            await self.bot.say("I need permissions to manage roles first.")
        except Exception as e:
            print(e)
            await self.bot.say("Something went wrong.")

    @editrole.command(name="name", pass_context=True)
    @checks.admin_or_permissions(administrator=True)
    async def edit_role_name(self, ctx, role: discord.Role, name: str):
        """Edits a role's name

        Use double quotes if the role or the name contain spaces.
        Examples:
        !editrole name \"The Transistor\" Test"""
        if name == "":
            await self.bot.say("Name cannot be empty.")
            return
        try:
            author = ctx.message.author
            old_name = role.name  # probably not necessary?
            await self.bot.edit_role(ctx.message.server, role, name=name)
            logger.info("{}({}) changed the name of role '{}' to '{}'".format(
                author.name, author.id, old_name, name))
            await self.bot.say("Done.")
        except discord.Forbidden:
            await self.bot.say("I need permissions to manage roles first.")
        except Exception as e:
            print(e)
            await self.bot.say("Something went wrong.")

    @commands.command()
    async def names(self, user : discord.Member):
        """Show previous names/nicknames of a user"""
        server = user.server
        names = self.past_names[user.id] if user.id in self.past_names else None
        try:
            nicks = self.past_nicknames[server.id][user.id]
            nicks = [escape_mass_mentions(nick) for nick in nicks]
        except:
            nicks = None
        msg = ""
        if names:
            names = [escape_mass_mentions(name) for name in names]
            msg += "**Past 20 names**:\n"
            msg += ", ".join(names)
        if nicks:
            if msg:
                msg += "\n\n"
            msg += "**Past 20 nicknames**:\n"
            msg += ", ".join(nicks)
        if msg:
            await self.bot.say(msg)
        else:
            await self.bot.say("That user doesn't have any recorded name or "
                               "nickname change.")

    def discordpy_updated(self):
        try:
            assert self.bot.purge_from
        except:
            return False
        return True

    async def _delete_message(self, message):
        try:
            await self.bot.delete_message(message)
        except discord.errors.NotFound:
            pass
        except:
            raise

    def immune_from_filter(self, message):
        user = message.author
        server = message.server
        admin_role = settings.get_server_admin(server)
        mod_role = settings.get_server_mod(server)

        if user.id == settings.owner:
            return True
        elif discord.utils.get(user.roles, name=admin_role):
            return True
        elif discord.utils.get(user.roles, name=mod_role):
            return True
        else:
            return False

    async def check_filter(self, message):
        if message.channel.is_private:
            return
        server = message.server
        can_delete = message.channel.permissions_for(server.me).manage_messages

        if (message.author.id == self.bot.user.id or
        self.immune_from_filter(message) or not can_delete): # Owner, admins and mods are immune to the filter
            return

        if server.id in self.filter.keys():
            for w in self.filter[server.id]:
                if w in message.content.lower():
                    # Something else in discord.py is throwing a 404 error
                    # after deletion
                    try:
                        await self._delete_message(message)
                    except:
                        pass
                    print("Message deleted. Filtered: " + w)

    async def check_names(self, before, after):
        if before.name != after.name:
            if before.id not in self.past_names.keys():
                self.past_names[before.id] = [after.name]
            else:
                if after.name not in self.past_names[before.id]:
                    names = deque(self.past_names[before.id], maxlen=20)
                    names.append(after.name)
                    self.past_names[before.id] = list(names)
            dataIO.save_json("data/mod/past_names.json", self.past_names)

        if before.nick != after.nick and after.nick is not None:
            server = before.server
            if not server.id in self.past_nicknames:
                self.past_nicknames[server.id] = {}
            if before.id in self.past_nicknames[server.id]:
                nicks = deque(self.past_nicknames[server.id][before.id],
                              maxlen=20)
            else:
                nicks = []
            if after.nick not in nicks:
                nicks.append(after.nick)
                self.past_nicknames[server.id][before.id] = list(nicks)
                dataIO.save_json("data/mod/past_nicknames.json",
                                 self.past_nicknames)

def check_folders():
    folders = ("data", "data/mod/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_files():
    ignore_list = {"SERVERS": [], "CHANNELS": []}

    if not os.path.isfile("data/mod/blacklist.json"):
        print("Creating empty blacklist.json...")
        fileIO("data/mod/blacklist.json", "save", [])

    if not os.path.isfile("data/mod/whitelist.json"):
        print("Creating empty whitelist.json...")
        fileIO("data/mod/whitelist.json", "save", [])

    if not os.path.isfile("data/mod/ignorelist.json"):
        print("Creating empty ignorelist.json...")
        fileIO("data/mod/ignorelist.json", "save", ignore_list)

    if not os.path.isfile("data/mod/filter.json"):
        print("Creating empty filter.json...")
        fileIO("data/mod/filter.json", "save", {})

    if not os.path.isfile("data/mod/past_names.json"):
        print("Creating empty past_names.json...")
        fileIO("data/mod/past_names.json", "save", {})

    if not os.path.isfile("data/mod/past_nicknames.json"):
        print("Creating empty past_nicknames.json...")
        fileIO("data/mod/past_nicknames.json", "save", {})



def setup(bot):
    global logger
    check_folders()
    check_files()
    logger = logging.getLogger("mod")
    # Prevents the logger from being loaded again in case of module reload
    if logger.level == 0:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(
            filename='data/mod/mod.log', encoding='utf-8', mode='a')
        handler.setFormatter(
            logging.Formatter('%(asctime)s %(message)s', datefmt="[%d/%m/%Y %H:%M]"))
        logger.addHandler(handler)
    n = Mod(bot)
    bot.add_listener(n.check_filter, "on_message")
    bot.add_listener(n.check_names, "on_member_update")
    bot.add_cog(n)
