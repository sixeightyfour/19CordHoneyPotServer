import os
import discord
from discord.ext import tasks
from discord import app_commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
HONEYPOT_CHANNEL_ID = int(os.getenv("HONEYPOT_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.members = True          # Required to Kick
intents.message_content = True  # Required to Detect Messages
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

total_kicks = 0 # Total Kicks (For Measuring Number of Triggers)

def build_status_embed() -> discord.Embed:
    embed = discord.Embed(title="Honeypot Security Status", color=discord.Color.blue())
    embed.add_field(name="Monitored Channel ID", value=HONEYPOT_CHANNEL_ID, inline=False)
    embed.add_field(name="Total Bots Kicked", value=total_kicks, inline=False)
    return embed

@client.event
async def on_ready():
    print(f"Honey pot active as {client.user} ({client.user.id})")
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@client.event
async def on_message(message: discord.Message):
    global total_kicks

    # Ignore Bots own Messages, Messages From other Bots
    if message.author == client.user:
        return

    # Checks if Message was Sent in Restricted Channel
    if message.channel.id == HONEYPOT_CHANNEL_ID:

        # Logs Username and Message for Appeal Purposes
        user_info = f"User: {message.author} (ID: {message.author.id})"
        content_info = f"Message: {message.content}"
        
        try:
            # Produces Message in Dedicated Log Channel Using user_info and content_info
            log_channel = client.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(title="Honey Pot Kick Log", color=discord.Color.red())
                log_embed.add_field(name="Offender", value=user_info, inline=False)
                log_embed.add_field(name="Sent Content", value=content_info or "[No Text/Embed]", inline=False)
                
                log_file = None
                if message.attachments:
                    attachment = message.attachments[0]
                    # Converts Attachment into File Object to Re-Upload
                    log_file = await attachment.to_file()
                    # If an image, Embeds Re-Uploaded File
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        log_embed.set_image(url=f"attachment://{attachment.filename}")

                # Kicks User
                await message.author.kick(reason="Honey Pot: Unauthorized message in restricted channel.")
                total_kicks += 1
                print(f"[KICKED] {message.author} ({message.author.id})")
                
                # Sends Log to Log Channel
                log_channel = client.get_channel(LOG_CHANNEL_ID) or await client.fetch_channel(LOG_CHANNEL_ID)
            
                if log_channel:
                    # Attatches Embed (if Applicable)
                    await log_channel.send(embed=log_embed, file=log_file)
            
            # Deletes Message to Keep Channel Clean
            try:
                await message.delete()
            except discord.HTTPException:
                pass

        # Prevents Higher Role Users (Modstaff) from being Kicked 
        except discord.Forbidden:
            print(f"[ERROR] Could not kick {message.author}. Check role hierarchy.")
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")

@tree.command(name="honeypot_status", description="Show how many users have been kicked.")
async def status_command(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_status_embed())

@client.event
async def on_disconnect():
    print("Honeypot bot disconnected.")

async def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set.")
    if HONEYPOT_CHANNEL_ID == 0:
        raise RuntimeError("HONEYPOT_CHANNEL_ID is not set or invalid.")

    async with client:
        await client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
