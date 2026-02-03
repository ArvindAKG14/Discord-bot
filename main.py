# imports
import discord
import os
from discord.flags import Intents
from dotenv import load_dotenv
from discord.ext import commands
import sqlite3
from pymongo.mongo_client import MongoClient

# Load environment variables first
load_dotenv()

# MongoDB connection
mongo_uri = os.getenv('MONGO_URI')
print(f"MongoDB URI from environment: {mongo_uri}")
if mongo_uri:
    # Fix URI format if needed (replace # with ?)
    if '#' in mongo_uri and '?' not in mongo_uri:
        mongo_uri = mongo_uri.replace('#', '?')
        print(f"Fixed MongoDB URI format: {mongo_uri}")
    
    # Create a new client and connect to the server without SSL (for Replit compatibility)
    try:
        mongo_client = MongoClient(
            mongo_uri, 
            ssl=False,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )
    except Exception as ssl_error:
        print(f"SSL connection failed: {ssl_error}")
        # Fallback: try with basic SSL settings
        try:
            mongo_client = MongoClient(
                mongo_uri, 
                tls=True,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
        except Exception as fallback_error:
            print(f"Fallback connection also failed: {fallback_error}")
            mongo_client = None

    # Send a ping to confirm a successful connection
    try:
        mongo_client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
        mongo_db = mongo_client.get_database(
        )  # Uses default database from URI
        mongo_collection = mongo_db.server_members  # Collection name
    except Exception as e:
        print(e)
        mongo_client = None
        mongo_db = None
        mongo_collection = None
else:
    print("No MongoDB URI found in environment variables")
    mongo_client = None
    mongo_db = None
    mongo_collection = None

# SQLite connection (keeping existing functionality)
conn = sqlite3.connect('tennis.db')
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS server_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        has_general_role BOOLEAN DEFAULT 0,
        has_singles_role BOOLEAN DEFAULT 0,
        has_doubles_role BOOLEAN DEFAULT 0,
        UNIQUE(username)
    )
''')

# Add new columns to existing table if they don't exist
try:
    cursor.execute(
        'ALTER TABLE server_members ADD COLUMN has_singles_role BOOLEAN DEFAULT 0'
    )
except sqlite3.OperationalError:
    pass  # Column already exists

try:
    cursor.execute(
        'ALTER TABLE server_members ADD COLUMN has_doubles_role BOOLEAN DEFAULT 0'
    )
except sqlite3.OperationalError:
    pass  # Column already exists

conn.commit()

intents = Intents.default()
# Re-enable privileged intents (ensure they're enabled in Discord Developer Portal)
intents.message_content = True
intents.reactions = True
intents.members = True

client = commands.Bot(command_prefix='$bot ', intents=intents)


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

    # Sync members for all guilds the bot is in
    for guild in client.guilds:
        await sync_server_members(guild)

    # You can set this to your rules channel ID
    rules_channel_id = int(os.getenv('RULES_CHANNEL_ID', 0))

    if rules_channel_id:
        try:
            rules_channel = client.get_channel(rules_channel_id)
            if rules_channel:
                # Check if we already have both messages
                has_rules_message = False
                has_singles_doubles_message = False

                async for message in rules_channel.history(limit=100):
                    if message.author == client.user:
                        if message.content == "React to this message for your role":
                            has_rules_message = True
                        elif message.content == "React with 1️⃣ if you are playing singles or 2️⃣ if you are playing doubles":
                            has_singles_doubles_message = True

                # Send the rules message if it doesn't exist
                if not has_rules_message:
                    await rules_channel.send(
                        "React to this message for your role")
                    print(f"Rules message sent to {rules_channel.name}")

                # Send the singles/doubles selection message if it doesn't exist
                if not has_singles_doubles_message:
                    message = await rules_channel.send(
                        "React with 1️⃣ if you are playing singles or 2️⃣ if you are playing doubles"
                    )
                    print(
                        f"Singles/doubles message sent to {rules_channel.name}"
                    )
            else:
                print(f"Could not find channel with ID {rules_channel_id}")
        except Exception as e:
            print(f"Error sending rules message: {e}")


@client.listen('on_message')
async def handle_message(message):
    if message.author == client.user:
        return
    if message.content.startswith('$bot hello'):
        await message.channel.send('Hello!')
    elif message.content.startswith('$bot greet'):
        await message.channel.send('Hello ' + message.author.name)
    elif message.content.startswith('$bot database'):
        try:
            # First, check for any members in the server who aren't in the database
            for member in message.guild.members:
                if not member.bot:  # Skip bots
                    cursor.execute(
                        'SELECT * FROM server_members WHERE username = ?',
                        (member.name, ))
                    if not cursor.fetchone():
                        # Member not found in database, add them
                        general_role = discord.utils.get(message.guild.roles,
                                                         name="general")
                        singles_role = discord.utils.get(message.guild.roles,
                                                         name="singles")
                        doubles_role = discord.utils.get(message.guild.roles,
                                                         name="doubles")

                        has_general = general_role in member.roles if general_role else False
                        has_singles = singles_role in member.roles if singles_role else False
                        has_doubles = doubles_role in member.roles if doubles_role else False

                        cursor.execute(
                            '''
                            INSERT INTO server_members 
                            (username, has_general_role, has_singles_role, has_doubles_role) 
                            VALUES (?, ?, ?, ?)
                        ''',
                            (member.name, 1 if has_general else 0,
                             1 if has_singles else 0, 1 if has_doubles else 0))
                        conn.commit()
                        print(
                            f"Added missing member {member.name} to database")

            cursor.execute('SELECT * FROM server_members')
            rows = cursor.fetchall()
            if rows:
                # Create a formatted message
                response = "**Tennis Database Contents:**\n```"
                response += "ID | Username | General | Singles | Doubles\n"
                response += "-" * 80 + "\n"

                for row in rows:
                    general_text = f"{row[2]} {'(True)' if row[2] == 1 else '(False)'}"
                    singles_text = f"{row[3]} {'(True)' if row[3] == 1 else '(False)'}" if len(
                        row) > 3 else "0 (False)"
                    doubles_text = f"{row[4]} {'(True)' if row[4] == 1 else '(False)'}" if len(
                        row) > 4 else "0 (False)"
                    response += f"{row[0]} | {row[1]} | {general_text} | {singles_text} | {doubles_text}\n"

                response += "```"
                await message.channel.send(response)
            else:
                await message.channel.send("The database is empty!")
        except Exception as e:
            await message.channel.send(f"Error accessing database: {e}")
    elif message.content.startswith('$bot promote'):
        # Check if user has permission to manage roles
        if not message.author.guild_permissions.manage_roles:
            await message.channel.send(
                "You don't have permission to manage roles.")
            return

        # Split the command into parts
        parts = message.content.split()

        # Check if the command has the correct format
        if len(parts) < 4:
            await message.channel.send(
                "Usage: $bot promote [@player] [role_name]")
            return

        # Get the mentioned user
        if len(message.mentions) == 0:
            await message.channel.send("Please mention a user to promote.")
            return

        target_user = message.mentions[0]

        # Get the role name by joining all parts after the user mention
        role_name = ' '.join(parts[3:])

        # Find the role in the server
        role = discord.utils.get(message.guild.roles, name=role_name)

        if role is None:
            await message.channel.send(f"Role '{role_name}' not found.")
            return

        # Check if the user already has the role
        if role in target_user.roles:
            await message.channel.send(
                f"{target_user.display_name} already has the role '{role_name}'."
            )
            return

        try:
            # Add the role to the user
            await target_user.add_roles(role)
            await message.channel.send(
                f"Successfully assigned the role '{role_name}' to {target_user.display_name}!"
            )
        except discord.Forbidden:
            await message.channel.send(
                "I don't have permission to assign that role.")
        except discord.HTTPException:
            await message.channel.send(
                "An error occurred while assigning the role.")

    elif message.content.startswith('$bot demote'):
        # Check if user has permission to manage roles
        if not message.author.guild_permissions.manage_roles:
            await message.channel.send(
                "You don't have permission to manage roles.")
            return

        # Split the command into parts
        parts = message.content.split()

        # Check if the command has the correct format
        if len(parts) < 4:
            await message.channel.send(
                "Usage: $bot demote [@player] [role_name]")
            return

        # Get the mentioned user
        if len(message.mentions) == 0:
            await message.channel.send("Please mention a user to demote.")
            return

        target_user = message.mentions[0]

        # Get the role name by joining all parts after the user mention
        role_name = ' '.join(parts[3:])

        # Find the role in the server
        role = discord.utils.get(message.guild.roles, name=role_name)

        if role is None:
            await message.channel.send(f"Role '{role_name}' not found.")
            return

        # Check if the user has the role
        if role not in target_user.roles:
            await message.channel.send(
                f"{target_user.display_name} doesn't have the role '{role_name}'."
            )
            return

        try:
            # Remove the role from the user
            await target_user.remove_roles(role)
            await message.channel.send(
                f"Successfully removed the role '{role_name}' from {target_user.display_name}!"
            )
        except discord.Forbidden:
            await message.channel.send(
                "I don't have permission to remove that role.")
        except discord.HTTPException:
            await message.channel.send(
                "An error occurred while removing the role.")


@client.event
async def on_raw_reaction_add(payload):
    # Skip if the reaction is from the bot itself
    if payload.user_id == client.user.id:
        return

    # Get the channel where the reaction was added
    channel = client.get_channel(payload.channel_id)

    if not channel:
        return

    # Get the message that was reacted to
    try:
        message = await channel.fetch_message(payload.message_id)

        # Check if the message is from the bot and has the expected content
        if message.author.id == client.user.id:
            guild = client.get_guild(payload.guild_id)
            if not guild:
                return

            member = guild.get_member(payload.user_id)
            if not member:
                return

            # Handle general role assignment
            if message.content == "React to this message for your role":
                # Check if the reaction is the white_check_mark emoji
                if str(payload.emoji) == "✅":
                    # Get the general role
                    role = discord.utils.get(guild.roles, name="general")

                    # If the role doesn't exist, create it
                    if not role:
                        try:
                            role = await guild.create_role(name="general")
                            print(f"Created 'general' role")
                        except discord.Forbidden:
                            print(
                                "Bot doesn't have permission to create roles")
                            return
                        except Exception as e:
                            print(f"Error creating role: {e}")
                            return

                    # Assign the role
                    if role not in member.roles:
                        try:
                            await member.add_roles(role)
                            print(
                                f"Assigned 'general' role to {member.display_name}"
                            )
                        except discord.Forbidden:
                            print(
                                "Bot doesn't have permission to assign roles")
                        except Exception as e:
                            print(f"Error assigning role: {e}")

            # Handle singles/doubles role assignment
            elif message.content == "React with 1️⃣ if you are playing singles or 2️⃣ if you are playing doubles":
                role_name = None

                if str(payload.emoji) == "1️⃣":
                    role_name = "singles"
                elif str(payload.emoji) == "2️⃣":
                    role_name = "doubles"

                if role_name:
                    # Get or create the role
                    role = discord.utils.get(guild.roles, name=role_name)

                    if not role:
                        try:
                            role = await guild.create_role(name=role_name)
                            print(f"Created '{role_name}' role")
                        except discord.Forbidden:
                            print(
                                "Bot doesn't have permission to create roles")
                            return
                        except Exception as e:
                            print(f"Error creating role: {e}")
                            return

                    # Assign the role
                    if role not in member.roles:
                        try:
                            await member.add_roles(role)
                            print(
                                f"Assigned '{role_name}' role to {member.display_name}"
                            )

                            # Update database
                            if role_name == "singles":
                                cursor.execute(
                                    'UPDATE server_members SET has_singles_role = 1 WHERE username = ?',
                                    (member.name, ))
                            elif role_name == "doubles":
                                cursor.execute(
                                    'UPDATE server_members SET has_doubles_role = 1 WHERE username = ?',
                                    (member.name, ))
                            conn.commit()
                        except discord.Forbidden:
                            print(
                                "Bot doesn't have permission to assign roles")
                        except Exception as e:
                            print(f"Error assigning role: {e}")
    except Exception as e:
        print(f"Error processing reaction: {e}")


@client.event
async def on_raw_reaction_remove(payload):
    # Skip if the reaction is from the bot itself
    if payload.user_id == client.user.id:
        return

    # Get the channel where the reaction was removed
    channel = client.get_channel(payload.channel_id)

    if not channel:
        return

    # Get the message that was reacted to
    try:
        message = await channel.fetch_message(payload.message_id)

        # Check if the message is from the bot and has the expected content
        if message.author.id == client.user.id:
            guild = client.get_guild(payload.guild_id)
            if not guild:
                return

            member = guild.get_member(payload.user_id)
            if not member:
                return

            # Handle general role removal
            if message.content == "React to this message for your role":
                # Check if the reaction is the white_check_mark emoji
                if str(payload.emoji) == "✅":
                    # Get the general role
                    role = discord.utils.get(guild.roles, name="general")
                    if not role:
                        return

                    # Remove the role
                    if role in member.roles:
                        try:
                            await member.remove_roles(role)
                            print(
                                f"Removed 'general' role from {member.display_name}"
                            )
                        except discord.Forbidden:
                            print(
                                "Bot doesn't have permission to remove roles")
                        except Exception as e:
                            print(f"Error removing role: {e}")

            # Handle singles/doubles role removal
            elif message.content == "React with 1️⃣ if you are playing singles or 2️⃣ if you are playing doubles":
                role_name = None

                if str(payload.emoji) == "1️⃣":
                    role_name = "singles"
                elif str(payload.emoji) == "2️⃣":
                    role_name = "doubles"

                if role_name:
                    # Get the role
                    role = discord.utils.get(guild.roles, name=role_name)
                    if not role:
                        return

                    # Remove the role
                    if role in member.roles:
                        try:
                            await member.remove_roles(role)
                            print(
                                f"Removed '{role_name}' role from {member.display_name}"
                            )

                            # Update database
                            if role_name == "singles":
                                cursor.execute(
                                    'UPDATE server_members SET has_singles_role = 0 WHERE username = ?',
                                    (member.name, ))
                            elif role_name == "doubles":
                                cursor.execute(
                                    'UPDATE server_members SET has_doubles_role = 0 WHERE username = ?',
                                    (member.name, ))
                            conn.commit()
                        except discord.Forbidden:
                            print(
                                "Bot doesn't have permission to remove roles")
                        except Exception as e:
                            print(f"Error removing role: {e}")
    except Exception as e:
        print(f"Error processing reaction removal: {e}")


async def sync_server_members(guild):
    try:
        general_role = discord.utils.get(guild.roles, name="general")
        singles_role = discord.utils.get(guild.roles, name="singles")
        doubles_role = discord.utils.get(guild.roles, name="doubles")

        for member in guild.members:
            if not member.bot:  # Skip bots
                has_general = general_role in member.roles if general_role else False
                has_singles = singles_role in member.roles if singles_role else False
                has_doubles = doubles_role in member.roles if doubles_role else False

                cursor.execute(
                    '''
                    INSERT OR REPLACE INTO server_members 
                    (username, has_general_role, has_singles_role, has_doubles_role) 
                    VALUES (?, ?, ?, ?)
                ''', (member.name, 1 if has_general else 0,
                      1 if has_singles else 0, 1 if has_doubles else 0))
        conn.commit()
        print(f"Synced {len(guild.members)} members from {guild.name}")
    except Exception as e:
        print(f"Error syncing members: {e}")


client.run(os.getenv('TOKEN'))
