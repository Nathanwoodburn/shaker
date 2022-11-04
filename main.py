import base64
import disnake
import dns.resolver
import dns.exception
import dns.message
import json
import os
import re
from disnake.ext import commands
from dotenv import load_dotenv


load_dotenv()

resolver = dns.resolver.Resolver(configure=False)
resolver.nameservers = ["127.0.0.1"]

intents = disnake.Intents.default()
intents.members = True

bot = commands.InteractionBot(intents=intents)


def check_name(user_id: int, name: str) -> bool:
    try:
        answer = resolver.resolve('_shaker._auth.' + name, 'TXT')
        for rrset in answer.response.answer:
            parts = rrset.to_text().split(" ")
            if str(user_id) in parts[-1]:
                return True
    except dns.exception.DNSException:
        pass

    return False


async def handle_role(member: disnake.Member, shouldHaveRole: bool) -> None:
    with open('roles.json', 'r') as f:
        roles = json.load(f)

    key = str(member.guild.id)

    if not key in roles:
        return

    role_id = roles[key]

    if role_id:
        guild = member.guild
        role = guild.get_role(role_id)
        if role and shouldHaveRole and not role in member.roles:
            await member.add_roles(role)
        elif role and not shouldHaveRole and role in member.roles:
            await member.remove_roles(role)


async def check_member(member: disnake.Member) -> bool:
    if member.display_name[-1] != "/":
        await handle_role(member, False)
        return

    if check_name(member.id, member.display_name[0:-1]):
        await handle_role(member, True)
        return True
    
    try:
        await member.edit(nick=member.display_name[0:-1])
    except disnake.errors.Forbidden:
        pass
    await handle_role(member, False)
    return False


@bot.listen()
async def on_raw_member_update(member: disnake.Member) -> None:
    await check_member(member)


@bot.listen()
async def on_member_join(member: disnake.Member) -> None:
    await check_member(member)


@bot.slash_command(dm_permission=False)
@commands.default_member_permissions(manage_guild=True)
async def setverifiedrole(
    inter: disnake.ApplicationCommandInteraction,
    role: disnake.Role
):
    """
    Sets the role to be given when members verify.

    Parameters
    ----------
    role: The role to be given when members verify.
    """

    if not inter.guild.me.guild_permissions.manage_roles:
        return await inter.response.send_message("I do not have permission to add roles to members.", ephemeral=True)

    if inter.guild.me.roles[-1] <= role:
        return await inter.response.send_message(f"I cannot give members this role. Try moving my role above <@&{role.id}> in the role settings page.", ephemeral=True)

    with open('roles.json', 'r') as f:
        roles = json.load(f)

    roles[str(inter.guild_id)] = role.id

    with open('roles.json', 'w') as f:
        json.dump(roles, f, indent=4)

    return await inter.response.send_message(f"The verified role has been set to <@&{role.id}>.", ephemeral=True)


@bot.slash_command(dm_permission=False)
async def verify(
    inter: disnake.ApplicationCommandInteraction,
    name: str
):
    """
    Verifies your ownership of a Handshake name and sets your nickname.

    Parameters
    ----------
    name: The Handshake name you'd like to verify ownership of.
    """

    name_idna = name.lower().strip().rstrip("/").encode("idna")

    name_ascii = name_idna.decode("ascii")

    parts = name_ascii.split(".")

    for part in parts:
        if not re.match(r'[A-Za-z0-9-_]+$', part):
            return await inter.response.send_message(f"`{name}` is not a valid Handshake name.", ephemeral=True)

    try:
        name_rendered = name_idna.decode("idna")
    except UnicodeError: # don't render invalid punycode
        name_rendered = name_ascii


    if check_name(inter.author.id, name_ascii):
        try:
            await inter.author.edit(nick=name_rendered + "/")
            await handle_role(inter.author, True)
            return await inter.response.send_message(f"Your display name has been set to `{name_rendered}/`", ephemeral=True)
        except disnake.errors.Forbidden:
            return await inter.response.send_message("I could not set your nickname because I do not have permission to. (Are you the server owner?)", ephemeral=True)

    records = [{
            "type": 'TXT',
            "host": ".".join(["_shaker", "_auth"] + parts[:-1]),
            "value": str(inter.author.id),
            "ttl": 60,
    }]

    records = json.dumps(records)
    records = records.encode("utf-8")
    records = base64.b64encode(records)
    records = records.decode("utf-8")

    await inter.response.send_message(
        f"To verify that you own `{name_rendered}/` please create a TXT record located at `_shaker._auth.{name_ascii}` with the following data: `{inter.author.id}`.\n\n"
        f"If you use Namebase, you can do this automatically by visiting the following link:\n"
        f"<https://namebase.io/next/domain-manager/{parts[-1]}/records?records={records}>\n\n"
        f"Once the record is set (this may take a few minutes) you can run this command again or manually set your nickname to `{name_rendered}/`.",
	ephemeral=True
    )


bot.run(os.getenv("DISCORD_TOKEN"))
