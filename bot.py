import os
import discord
from discord import app_commands
from discord.ext import commands
import redis

# --- ENVIRONMENT VARIABLES ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

# Yetkili Roller
ALLOWED_ROLES = [1444746663150223561, 1337512939586060293, 1337512939573219384]

# --- REDIS VERİTABANI BAĞLANTISI ---
r = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None


def get_user_points(user_id: str) -> int:
    points = r.hget("puanlar", user_id)
    return int(points) if points else 0


def add_user_points(user_id: str, amount: int) -> int:
    return r.hincrby("puanlar", user_id, amount)


def sub_user_points(user_id: str, amount: int) -> int:
    # Negatif miktar göndererek puan düşüyoruz
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
        print(" Slash komutları başarıyla senkronize edildi.")


bot = PointBot()


# --- YETKİ KONTROL FONKSİYONU ---
def has_required_role(interaction: discord.Interaction) -> bool:
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in user_role_ids for role_id in ALLOWED_ROLES)


# --- SİYAH EMBED OLUŞTURUCU ---
def create_black_embed(title: str, description: str = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏛️ **{title}**",
        description=description,
        color=discord.Color.from_rgb(1, 1, 1),
    )
    embed.set_footer(
        text="Puan Yönetim Sistemi",
        icon_url=bot.user.avatar.url if bot.user and bot.user.avatar else None,
    )
    return embed


# --- KOMUTLAR ---


# 1. /puanekle
@bot.tree.command(
    name="puanekle", description="Belirtilen kullanıcıya puan ekler."
)
@app_commands.describe(
    kullanici="Puan eklenecek üye", miktar="Eklenecek puan (1-100)"
)
async def puan_ekle(
    interaction: discord.Interaction, kullanici: discord.Member, miktar: int
):
    if not has_required_role(interaction):
        embed = create_black_embed(
            "Yetki Reddedildi",
            "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if miktar < 1 or miktar > 100:
        embed = create_black_embed(
            "İşlem Başarısız",
            "⚠️ Tek seferde **en az 1**, **en fazla 100** puan ekleyebilirsiniz.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    user_id = str(kullanici.id)
    new_points = add_user_points(user_id, miktar)

    embed = create_black_embed("Puan Ekleme İşlemi Başarılı")
    embed.add_field(
        name="Hedef Kullanıcı", value=kullanici.mention, inline=True
    )
    embed.add_field(name="Eklenen Puan", value=f"`+{miktar}`", inline=True)
    embed.add_field(
        name="Güncel Toplam Puan", value=f"`{new_points}` Puan", inline=False
    )

    await interaction.response.send_message(embed=embed)


# 2. /puancek
@bot.tree.command(
    name="puancek", description="Belirtilen kullanıcıdan puan eksiltir."
)
@app_commands.describe(
    kullanici="Puan düşülecek üye", miktar="Eksiltilecek puan (1-100)"
)
async def puan_cek(
    interaction: discord.Interaction, kullanici: discord.Member, miktar: int
):
    if not has_required_role(interaction):
        embed = create_black_embed(
            "Yetki Reddedildi",
            "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if miktar < 1 or miktar > 100:
        embed = create_black_embed(
            "İşlem Başarısız",
            "⚠️ Tek seferde **en az 1**, **en fazla 100** puan eksiltebilirsiniz.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    user_id = str(kullanici.id)
    new_points = sub_user_points(user_id, miktar)

    embed = create_black_embed("Puan Eksiltme İşlemi Başarılı")
    embed.add_field(
        name="Hedef Kullanıcı", value=kullanici.mention, inline=True
    )
    embed.add_field(name="Eksiltilen Puan", value=f"`-{miktar}`", inline=True)
    embed.add_field(
        name="Güncel Toplam Puan", value=f"`{new_points}` Puan", inline=False
    )

    await interaction.response.send_message(embed=embed)


# 3. /puansorgu
@bot.tree.command(
    name="puansorgu", description="Bir kullanıcının mevcut puanını sorgular."
)
@app_commands.describe(
    kullanici="Puanı sorgulanacak üye (Boş bırakılırsa kendiniz)"
)
async def puan_sorgu(
    interaction: discord.Interaction, kullanici: discord.Member = None
):
    if not has_required_role(interaction):
        embed = create_black_embed(
            "Yetki Reddedildi",
            "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    target = kullanici or interaction.user
    user_points = get_user_points(str(target.id))

    embed = create_black_embed("Puan Sorgulama Raporu")
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(
        name="Sorgulanan Kullanıcı", value=target.mention, inline=True
    )
    embed.add_field(
        name="Mevcut Puan", value=f"`{user_points}` Puan", inline=True
    )

    await interaction.response.send_message(embed=embed)


# 4. /toplupuan
@bot.tree.command(
    name="toplupuan",
    description="Sistemde puanı olan tüm üyelerin dökümünü verir.",
)
async def toplu_puan(interaction: discord.Interaction):
    if not has_required_role(interaction):
        embed = create_black_embed(
            "Yetki Reddedildi",
            "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    points = get_all_points()
    if not points:
        embed = create_black_embed(
            "Kayıt Bulunamadı",
            "Sistemde henüz puan tanımı yapılmış bir kullanıcı bulunmamaktadır.",
        )
        await interaction.response.send_message(embed=embed)
        return

    all_users = list(points.items())

    chunk_size = 15
    chunks = [
        all_users[i : i + chunk_size]
        for i in range(0, len(all_users), chunk_size)
    ]

    await interaction.response.defer()

    for page, chunk in enumerate(chunks, start=1):
        list_text = ""
        for user_id, p_amount in chunk:
            list_text += f"• <@{user_id}> — `{p_amount}` Puan\n"

        title = "Tüm Üyelerin Puan Dökümü"
        if len(chunks) > 1:
            title += f" (Sayfa {page}/{len(chunks)})"

        embed = create_black_embed(title, list_text)

        if page == 1:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.channel.send(embed=embed)


# 5. /puansifirla (Bireysel Sıfırlama)
@bot.tree.command(
    name="puansifirla", description="Belirtilen üyenin puanını sıfırlar."
)
@app_commands.describe(kullanici="Puanı sıfırlanacak üye")
async def puan_sifirla(
    interaction: discord.Interaction, kullanici: discord.Member
):
    if not has_required_role(interaction):
        embed = create_black_embed(
            "Yetki Reddedildi",
            "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    user_id = str(kullanici.id)
    reset_user_points(user_id)

    embed = create_black_embed("Puan Sıfırlama Başarılı")
    embed.add_field(
        name="İşlem Yapılan Kullanıcı", value=kullanici.mention, inline=True
    )
    embed.add_field(name="Güncel Puan", value="`0` Puan", inline=True)

    await interaction.response.send_message(embed=embed)


# 6. /toplusifirla (Tüm Sistem Sıfırlama)
@bot.tree.command(
    name="toplusifirla",
    description="Sistemdeki TÜM üyelerin puanlarını sıfırlar.",
)
async def toplu_sifirla(interaction: discord.Interaction):
    if not has_required_role(interaction):
        embed = create_black_embed(
            "Yetki Reddedildi",
            "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    reset_all_points()

    embed = create_black_embed(
        "Sistem Geneli Sıfırlama Tamamlandı",
        "⚠️ Veritabanındaki tüm puan kayıtları temizlenmiştir.",
    )
    await interaction.response.send_message(embed=embed)


# --- BOTU BAŞLAT ---
@bot.event
async def on_ready():
    print(
        f"✅ {bot.user.name} olarak giriş yapıldı ve Redis bağlantısı aktif!"
    )


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ HATA: BOT_TOKEN çevre değişkeni bulunamadı!")
    elif not REDIS_URL:
        print("❌ HATA: REDIS_URL çevre değişkeni bulunamadı!")
    else:
        bot.run(BOT_TOKEN)
