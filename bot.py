import os
import discord
from discord import app_commands
from discord.ext import commands
import redis

# --- AYARLAR ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

# Yetkili Rol ID'lerin (Bunları kendi sunucundaki ID'ler ile değiştirebilirsin)
ALLOWED_ROLES = [1444746663150223561, 1337512939586060293, 1337512939573219384]

# --- REDIS BAĞLANTISI ---
# decode_responses=True sayesinde Redis'ten gelen veriler otomatik string olur
r = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None

# --- VERİTABANI İŞLEMLERİ ---
def get_user_points(user_id: str) -> int:
    points = r.hget("puanlar", user_id)
    return int(points) if points else 0

def add_user_points(user_id: str, amount: int) -> int:
    return r.hincrby("puanlar", user_id, amount)

def sub_user_points(user_id: str, amount: int) -> int:
    # Negatif değer göndererek puan düşürüyoruz
    return r.hincrby("puanlar", user_id, -amount)

def reset_user_points(user_id: str):
    r.hdel("puanlar", user_id)

def reset_all_points():
    r.delete("puanlar")

def get_all_points() -> dict:
    all_data = r.hgetall("puanlar")
    return {user_id: int(points) for user_id, points in all_data.items()}

# --- BOT KURULUMU ---
class PointBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash komutları senkronize edildi.")

bot = PointBot()

# --- YARDIMCI FONKSİYONLAR ---
def has_required_role(interaction: discord.Interaction) -> bool:
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in user_role_ids for role_id in ALLOWED_ROLES)

def create_black_embed(title: str, description: str = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏛️ **{title}**",
        description=description,
        color=discord.Color(0x000000), # Siyah renk
    )
    embed.set_footer(text="Puan Yönetim Sistemi", icon_url=bot.user.avatar.url if bot.user and bot.user.avatar else None)
    return embed

# --- KOMUTLAR ---

@bot.tree.command(name="puanekle", description="Belirtilen kullanıcıya puan ekler.")
@app_commands.describe(kullanici="Puan eklenecek üye", miktar="Eklenecek puan miktarı")
async def puan_ekle(interaction: discord.Interaction, kullanici: discord.Member, miktar: int):
    if not has_required_role(interaction):
        await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
        return

    new_points = add_user_points(str(kullanici.id), miktar)
    embed = create_black_embed("İşlem Başarılı", f"{kullanici.mention} kullanıcısına `{miktar}` puan eklendi.\nGüncel puan: `{new_points}`")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="puancek", description="Belirtilen kullanıcıdan puan eksiltir.")
@app_commands.describe(kullanici="Puan düşülecek üye", miktar="Eksiltilecek puan miktarı")
async def puan_cek(interaction: discord.Interaction, kullanici: discord.Member, miktar: int):
    if not has_required_role(interaction):
        await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
        return

    new_points = sub_user_points(str(kullanici.id), miktar)
    embed = create_black_embed("İşlem Başarılı", f"{kullanici.mention} kullanıcısından `{miktar}` puan düşüldü.\nGüncel puan: `{new_points}`")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="puansorgu", description="Bir kullanıcının puanını sorgular.")
@app_commands.describe(kullanici="Puanı sorgulanacak üye (boşsa kendiniz)")
async def puan_sorgu(interaction: discord.Interaction, kullanici: discord.Member = None):
    target = kullanici or interaction.user
    user_points = get_user_points(str(target.id))
    embed = create_black_embed("Puan Sorgulama", f"{target.mention} kullanıcısının puanı: `{user_points}`")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="toplupuan", description="Tüm kullanıcıların puan dökümünü verir.")
async def toplu_puan(interaction: discord.Interaction):
    points = get_all_points()
    if not points:
        await interaction.response.send_message("Sistemde kayıtlı puan bulunamadı.", ephemeral=True)
        return
    
    text = "\n".join([f"• <@{uid}> — `{p}` Puan" for uid, p in points.items()])
    embed = create_black_embed("Tüm Üyelerin Puan Dökümü", text)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="puansifirla", description="Belirtilen üyenin puanını sıfırlar.")
async def puan_sifirla(interaction: discord.Interaction, kullanici: discord.Member):
    if not has_required_role(interaction):
        await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
        return
    reset_user_points(str(kullanici.id))
    await interaction.response.send_message(f"✅ {kullanici.mention} puanı sıfırlandı.", embed=create_black_embed("Sıfırlama Başarılı"))

@bot.tree.command(name="toplusifirla", description="Tüm puanları sıfırlar.")
async def toplu_sifirla(interaction: discord.Interaction):
    if not has_required_role(interaction):
        await interaction.response.send_message("❌ Yetkiniz yok.", ephemeral=True)
        return
    reset_all_points()
    await interaction.response.send_message("⚠️ Tüm sistem puanları sıfırlandı.", embed=create_black_embed("Sistem Temizlendi"))

# --- BAŞLANGIÇ ---
@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} hazır!")

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
