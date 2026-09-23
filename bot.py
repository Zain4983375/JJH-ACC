import discord
from discord.ext import commands
import os
from datetime import datetime

# ============================================================
#  CONFIG
# ============================================================
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", ".")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.txt")
USED_FILE = os.path.join(DATA_DIR, "used.txt")
ALLOWED_USERS_FILE = os.path.join(DATA_DIR, "allowed_users.txt")

ALLOWED_CHANNEL_ID = None

# ============================================================
#  BOT SETUP
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ============================================================
#  FILE HELPERS
# ============================================================
def load_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [l.rstrip("\n") for l in f if l.strip()]


def save_lines(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for l in lines:
            f.write(l + "\n")


def append_line(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def parse_line(line: str):
    line = line.strip()
    if "|" not in line:
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2:
        return None
    if ":" not in parts[0] or ":" not in parts[1]:
        return None
    mail = parts[0].split(":", 1)[1].strip()
    password = parts[1].split(":", 1)[1].strip()
    if not mail or not password:
        return None
    return mail, password


# ---- allowed users helpers ----
def load_allowed_users():
    return set(load_lines(ALLOWED_USERS_FILE))


def save_allowed_users(users_set):
    save_lines(ALLOWED_USERS_FILE, list(users_set))


def is_allowed(user, author_id: int) -> bool:
    if isinstance(user, discord.Member) and user.guild_permissions.administrator:
        return True
    return str(author_id) in load_allowed_users()


# ---- custom check: admin OR allowed ----
def is_admin_or_allowed():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        if str(ctx.author.id) in load_allowed_users():
            return True
        raise commands.CheckFailure("You do not have permission to use this command.")
    return commands.check(predicate)


# ============================================================
#  EVENTS
# ============================================================
@bot.event
async def on_ready():
    print("=" * 50)
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print(f"Data dir    : {DATA_DIR}")
    print(f"Stock file  : {ACCOUNTS_FILE}")
    print(f"Used file   : {USED_FILE}")
    print(f"Allowed file: {ALLOWED_USERS_FILE}")
    print("=" * 50)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if ALLOWED_CHANNEL_ID is not None and message.channel.id != ALLOWED_CHANNEL_ID:
        await bot.process_commands(message)
        return

    if message.content.strip().lower() == "d":
        if not is_allowed(message.author, message.author.id):
            await message.reply("You are not allowed to use this command.")
            return

        lines = load_lines(ACCOUNTS_FILE)

        if not lines:
            await message.reply("**No accounts**")
            return

        first = lines.pop(0)
        save_lines(ACCOUNTS_FILE, lines)

        parsed = parse_line(first)
        if not parsed:
            await message.reply("Corrupt account skipped. Type `d` again.")
            return

        mail, password = parsed

        append_line(
            USED_FILE,
            f"{mail} | {password} | {message.author} | {datetime.utcnow().isoformat()}"
        )

        text = (
            f"**Mail:-** {mail}\n"
            f"**Pass:-** {password}\n"
            f"**Mail Login Site:-** https://flowmail.cc/\n\n"
            f"**Note:-** Use same email password for flowmail and discord to login"
        )
        await message.reply(text)
        return

    await bot.process_commands(message)


# ============================================================
#  ACCOUNT COMMANDS
# ============================================================
@bot.command(name="add")
@is_admin_or_allowed()
async def add_accounts(ctx, *, data: str = None):
    if data is None and ctx.message.reference:
        try:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            data = ref_msg.content
        except Exception:
            data = None

    if not data:
        await ctx.send(
            "No data provided.\n"
            "Usage:\n"
            "```\n!add\n"
            "Mail: a@x.com | Pass: 123\n"
            "Mail: b@x.com | Pass: 456\n"
            "```"
        )
        return

    added, errors = 0, 0
    error_lines = []

    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            if parse_line(line):
                f.write(line + "\n")
                added += 1
            else:
                errors += 1
                error_lines.append(line)

    total = len(load_lines(ACCOUNTS_FILE))

    msg = f"Added: **{added}** | Skipped: **{errors}** | Total stock: **{total}**"
    if error_lines:
        preview = "\n".join(f"`{l[:60]}`" for l in error_lines[:5])
        msg += f"\n\n**Skipped lines:**\n{preview}"
        if len(error_lines) > 5:
            msg += f"\n...and {len(error_lines) - 5} more lines"

    await ctx.send(msg)


@bot.command(name="stock")
@is_admin_or_allowed()
async def stock(ctx):
    lines = load_lines(ACCOUNTS_FILE)
    used = load_lines(USED_FILE)
    await ctx.send(f"Available: **{len(lines)}** | Used: **{len(used)}**")


@bot.command(name="clear")
@is_admin_or_allowed()
async def clear_stock(ctx):
    save_lines(ACCOUNTS_FILE, [])
    await ctx.send("Stock cleared.")


@bot.command(name="used")
@is_admin_or_allowed()
async def used_cmd(ctx):
    used = load_lines(USED_FILE)
    if not used:
        await ctx.send("No used accounts.")
        return
    last = used[-10:]
    await ctx.send("**Last 10 used:**\n" + "\n".join(f"`{u}`" for u in last))


# ============================================================
#  PERMISSION COMMANDS (only admin)
# ============================================================
@bot.command(name="gp")
@commands.has_permissions(administrator=True)
async def grant_permission(ctx, member: discord.Member):
    allowed = load_allowed_users()
    if str(member.id) in allowed:
        await ctx.send(f"{member.mention} already has permission.")
        return
    allowed.add(str(member.id))
    save_allowed_users(allowed)
    await ctx.send(f"Granted full access to {member.mention}.")


@bot.command(name="gpr")
@commands.has_permissions(administrator=True)
async def revoke_permission(ctx, member: discord.Member):
    allowed = load_allowed_users()
    if str(member.id) not in allowed:
        await ctx.send(f"{member.mention} does not have permission.")
        return
    allowed.discard(str(member.id))
    save_allowed_users(allowed)
    await ctx.send(f"Revoked access from {member.mention}.")


@bot.command(name="gpl")
@commands.has_permissions(administrator=True)
async def list_permissions(ctx):
    allowed = load_allowed_users()
    if not allowed:
        await ctx.send("No users have permission yet.")
        return
    lines = []
    for uid in allowed:
        try:
            user = await bot.fetch_user(int(uid))
            lines.append(f"{user.mention} (`{uid}`)")
        except Exception:
            lines.append(f"`{uid}` (unknown user)")
    await ctx.send("**Allowed users:**\n" + "\n".join(lines))


@bot.command(name="gpclear")
@commands.has_permissions(administrator=True)
async def clear_permissions(ctx):
    save_allowed_users(set())
    await ctx.send("All permissions cleared.")


# ============================================================
#  ERROR HANDLER
# ============================================================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("You do not have permission to use this command.")
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command.")
        return
    raise error


# ============================================================
#  HELP
# ============================================================
@bot.command(name="help")
async def help_cmd(ctx):
    text = (
        "**Bot Commands**\n"
        "`d` -> Take an account\n"
        "`!add` -> Bulk add accounts\n"
        "`!stock` -> Available + Used count\n"
        "`!used` -> Last 10 used\n"
        "`!clear` -> Clear stock\n"
        "`!gp @user` -> Grant full access (admin)\n"
        "`!gpr @user` -> Revoke access (admin)\n"
        "`!gpl` -> List allowed users (admin)\n"
        "`!gpclear` -> Clear all permissions (admin)\n"
        "`!help` -> This message"
    )
    await ctx.send(text)


# ============================================================
#  RUN
# ============================================================
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN environment variable is not set.")
    bot.run(TOKEN)
