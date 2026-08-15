import os
import discord
from discord import app_commands
from discord.ext import commands
import redis

# --- ENVIRONMENT VARIABLES ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

# --- SABİTLER VE AYARLAR ---
ALLOWED_ROLES = [1444746663150223561, 1337512939586060293, 1337512939573219384]
NOTIFICATION_CHANNEL_ID = 1537093313642106901
MENTION_ROLES = [1444746663150223561, 1337512939586060293]

# Görseldeki Rütbe Sıralaması ve Puan Gereksinimleri
RANK_ORDER = ["Memur", "Polis Memuru", "Onbaşı", "Çavuş", "Üstçavuş", "Başçavuş"]

RANKS = {
    "Memur": 90,
    "Polis Memuru": 120,
    "Onbaşı": 105,
    "Çavuş": 135,
    "Üstçavuş": 150,
    "Başçavuş": 170
}

# --- REDIS VERİTABANI BAĞLANTISI ---
r = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None

# Veritabanı Yardımcı Fonksiyonları
def get_user_points(user_id: str) -> int:
    points = r.hget("puanlar", user_id)
    return int(points) if points else 0

def add_user_points(user_id: str, amount: int) -> int:
    return r.hincrby("puanlar", user_id, amount)

def sub_user_points(user_id: str, amount: int) -> int:
    return r.hincrby("puanlar", user_id, -amount)

def reset_user_points(user_id: str):
    r.hdel("puanlar", user_id)

def reset_all_points():
    r.delete("puanlar")
    r.delete("rutbeler")

def get_all_points() -> dict:
    all_data = r.hgetall("puanlar")
    return {user_id: int(points) for user_id, points in all_data.items()}

def get_user_rank(user_id: str) -> str:
    rank = r.hget("rutbeler", user_id)
    return rank if rank else "Memur"  # Varsayılan rütbe

def set_user_rank(user_id: str, rank: str):
    r.hset("rutbeler", user_id, rank)

# --- BOT KURULUMU ---
class PointBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash komutları başarıyla senkronize edildi.")

bot = PointBot()

# --- YARDIMCI FONKSİYONLAR ---
def has_required_role(interaction: discord.Interaction) -> bool:
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in user_role_ids for role_id in ALLOWED_ROLES)

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

# --- BUTON VE BİLDİRİM SİSTEMİ ---
class PromotionButton(discord.ui.View):
    def __init__(self, target_user: discord.Member, current_rank: str):
        super().__init__(timeout=None)  # Kalıcı buton
        self.target_user = target_user
        self.current_rank = current_rank

    @discord.ui.button(label="Terfi Verildi", style=discord.ButtonStyle.success, emoji="✅", custom_id="promotion_confirm_btn")
    async def promote_callback(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not has_required_role(interaction):
            await interaction.response.send_message("❌ Bu işlemi onaylamak için yetkiniz yok.", ephemeral=True)
            return

        user_id = str(self.target_user.id)
        
        # Sıradaki rütbeyi belirle
        if self.current_rank in RANK_ORDER:
            current_index = RANK_ORDER.index(self.current_rank)
            if current_index + 1 < len(RANK_ORDER):
                next_rank = RANK_ORDER[current_index + 1]
                set_user_rank(user_id, next_rank)
                reset_user_points(user_id) # Puan sıfırlanır

                # Butonu devre dışı bırak
                button.disabled = True
                button.label = f"Terfi Onaylandı ({next_rank})"
                button.style = discord.ButtonStyle.secondary
                await interaction.message.edit(view=self)

                confirm_embed = create_black_embed(
                    "Terfi İşlemi Onaylandı",
                    f"✅ {interaction.user.mention} tarafından onaylandı.\n\n"
                    f"👤 **Personel:** {self.target_user.mention}\n"
                    f"🎖️ **Yeni Rütbe:** `{next_rank}`\n"
                    f"🔄 **Puan Durumu:** Sıfırlandı (`0` Puan)"
                )
                await interaction.channel.send(embed=confirm_embed)
                await interaction.response.send_message("Terfi işlemi başarıyla tamamlandı ve rütbe yükseltildi.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Kullanıcı zaten en yüksek rütbede (Başçavuş).", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Tanımsız rütbe hatası.", ephemeral=True)

async def check_and_notify_rank(guild: discord.Guild, user: discord.Member, points: int):
    """Kullanıcının puanı mevcut rütbesinin hedefine ulaştıysa butonlu bildirim atar."""
    user_id = str(user.id)
    user_rank = get_user_rank(user_id)
    target_score = RANKS.get(user_rank)

    if target_score and points >= target_score:
        channel = guild.get_channel(NOTIFICATION_CHANNEL_ID)
        if channel:
            role_mentions = " ".join([f"<@&{rid}>" for rid in MENTION_ROLES])
            
            embed = create_black_embed("🎉 Terfi Gereksinimleri Tamamlandı!")
            embed.add_field(name="Kullanıcı", value=user.mention, inline=True)
            embed.add_field(name="Mevcut Rütbe", value=f"`{user_rank}`", inline=True)
            embed.add_field(name="Gereken Puan", value=f"`{target_score}`", inline=True)
            embed.add_field(name="Mevcut Puan", value=f"`{points}`", inline=True)
            
            content = f"{role_mentions}\n📢 {user.mention} kullanıcısı **{user_rank}** rütbesi için gerekli terfi puanını tamamlamıştır!"
            view = PromotionButton(user, user_rank)
            await channel.send(content=content, embed=embed, view=view)

# --- KOMUTLAR ---

# 1. /rutbeayarla (Yeni eklendi - 1 kere yapılır)
@bot.tree.command(name="rutbeayarla", description="Kullanıcının bot içerisindeki rütbesini ayarlar.")
@app_commands.describe(kullanici="Rütbesi ayarlanacak üye", rutbe="Atanacak rütbe")
@app_commands.choices(rutbe=[
    app_commands.Choice(name=r, value=r) for r in RANK_ORDER
])
async def rutbe_ayarla(interaction: discord.Interaction, kullanici: discord.Member, rutbe: app_commands.Choice[str]):
    if not has_required_role(interaction):
        embed = create_black_embed("Yetki Reddedildi", "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    set_user_rank(str(kullanici.id), rutbe.value)
    embed = create_black_embed("Rütbe Tanımlandı", f"{kullanici.mention} için rütbe **{rutbe.value}** (Hedef: `{RANKS[rutbe.value]}` Puan) olarak ayarlandı.")
    await interaction.response.send_message(embed=embed)

# 2. /puanekle
@bot.tree.command(name="puanekle", description="Belirtilen kullanıcıya puan ekler.")
@app_commands.describe(kullanici="Puan eklenecek üye", miktar="Eklenecek puan (1-100)")
async def puan_ekle(interaction: discord.Interaction, kullanici: discord.Member, miktar: int):
    if not has_required_role(interaction):
        embed = create_black_embed("Yetki Reddedildi", "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if miktar < 1 or miktar > 100:
        embed = create_black_embed("İşlem Başarısız", "⚠️ Tek seferde **en az 1**, **en fazla 100** puan ekleyebilirsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    user_id = str(kullanici.id)
    new_points = add_user_points(user_id, miktar)
    user_rank = get_user_rank(user_id)

    embed = create_black_embed("Puan Ekleme İşlemi Başarılı")
    embed.add_field(name="Hedef Kullanıcı", value=kullanici.mention, inline=True)
    embed.add_field(name="Mevcut Rütbe", value=f"`{user_rank}`", inline=True)
    embed.add_field(name="Eklenen Puan", value=f"`+{miktar}`", inline=True)
    embed.add_field(name="Güncel Puan", value=f"`{new_points}/{RANKS.get(user_rank, 0)}` Puan", inline=False)

    await interaction.response.send_message(embed=embed)

    # Otomatik Terfi Kontrolü
    await check_and_notify_rank(interaction.guild, kullanici, new_points)

# 3. /puancek
@bot.tree.command(name="puancek", description="Belirtilen kullanıcıdan puan eksiltir.")
@app_commands.describe(kullanici="Puan düşülecek üye", miktar="Eksiltilecek puan (1-100)")
async def puan_cek(interaction: discord.Interaction, kullanici: discord.Member, miktar: int):
    if not has_required_role(interaction):
        embed = create_black_embed("Yetki Reddedildi", "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if miktar < 1 or miktar > 100:
        embed = create_black_embed("İşlem Başarısız", "⚠️ Tek seferde **en az 1**, **en fazla 100** puan eksiltebilirsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    user_id = str(kullanici.id)
    new_points = sub_user_points(user_id, miktar)
    user_rank = get_user_rank(user_id)

    embed = create_black_embed("Puan Eksiltme İşlemi Başarılı")
    embed.add_field(name="Hedef Kullanıcı", value=kullanici.mention, inline=True)
    embed.add_field(name="Mevcut Rütbe", value=f"`{user_rank}`", inline=True)
    embed.add_field(name="Eksiltilen Puan", value=f"`-{miktar}`", inline=True)
    embed.add_field(name="Güncel Puan", value=f"`{new_points}/{RANKS.get(user_rank, 0)}` Puan", inline=False)

    await interaction.response.send_message(embed=embed)

# 4. /puansorgu
@bot.tree.command(name="puansorgu", description="Bir kullanıcının mevcut puanını ve rütbesini sorgular.")
@app_commands.describe(kullanici="Puanı sorgulanacak üye (Boş bırakılırsa kendiniz)")
async def puan_sorgu(interaction: discord.Interaction, kullanici: discord.Member = None):
    if not has_required_role(interaction):
        embed = create_black_embed("Yetki Reddedildi", "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    target = kullanici or interaction.user
    user_id = str(target.id)
    user_points = get_user_points(user_id)
    user_rank = get_user_rank(user_id)
    target_score = RANKS.get(user_rank, 0)

    embed = create_black_embed("Puan Sorgulama Raporu")
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Sorgulanan Kullanıcı", value=target.mention, inline=True)
    embed.add_field(name="Mevcut Rütbe", value=f"`{user_rank}`", inline=True)
    embed.add_field(name="Puan Durumu", value=f"`{user_points}/{target_score}` Puan", inline=True)

    await interaction.response.send_message(embed=embed)

# 5. /toplupuan
@bot.tree.command(name="toplupuan", description="Sistemde puanı olan tüm üyelerin dökümünü verir.")
async def toplu_puan(interaction: discord.Interaction):
    if not has_required_role(interaction):
        embed = create_black_embed("Yetki Reddedildi", "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    points = get_all_points()
    if not points:
        embed = create_black_embed("Kayıt Bulunamadı", "Sistemde henüz puan tanımı yapılmış bir kullanıcı bulunmamaktadır.")
        await interaction.response.send_message(embed=embed)
        return

    all_users = list(points.items())
    chunk_size = 15
    chunks = [all_users[i : i + chunk_size] for i in range(0, len(all_users), chunk_size)]

    await interaction.response.defer()

    for page, chunk in enumerate(chunks, start=1):
        list_text = ""
        for user_id, p_amount in chunk:
            u_rank = get_user_rank(user_id)
            list_text += f"• <@{user_id}> — `{u_rank}` | `{p_amount}/{RANKS.get(u_rank, 0)}` Puan\n"

        title = "Tüm Üyelerin Puan Dökümü"
        if len(chunks) > 1:
            title += f" (Sayfa {page}/{len(chunks)})"

        embed = create_black_embed(title, list_text)

        if page == 1:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.channel.send(embed=embed)

# 6. /puansifirla
@bot.tree.command(name="puansifirla", description="Belirtilen üyenin puanını sıfırlar.")
@app_commands.describe(kullanici="Puanı sıfırlanacak üye")
async def puan_sifirla(interaction: discord.Interaction, kullanici: discord.Member):
    if not has_required_role(interaction):
        embed = create_black_embed("Yetki Reddedildi", "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    reset_user_points(str(kullanici.id))

    embed = create_black_embed("Puan Sıfırlama Başarılı")
    embed.add_field(name="İşlem Yapılan Kullanıcı", value=kullanici.mention, inline=True)
    embed.add_field(name="Güncel Puan", value="`0` Puan", inline=True)

    await interaction.response.send_message(embed=embed)

# 7. /toplusifirla
@bot.tree.command(name="toplusifirla", description="Sistemdeki TÜM üyelerin puanlarını ve rütbelerini sıfırlar.")
async def toplu_sifirla(interaction: discord.Interaction):
    if not has_required_role(interaction):
        embed = create_black_embed("Yetki Reddedildi", "❌ Bu komutu kullanmak için gerekli rollere sahip değilsiniz.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    reset_all_points()

    embed = create_black_embed("Sistem Geneli Sıfırlama Tamamlandı", "⚠️ Veritabanındaki tüm puan ve rütbe kayıtları temizlenmiştir.")
    await interaction.response.send_message(embed=embed)

# --- BOTU BAŞLAT ---
@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} olarak giriş yapıldı ve Redis bağlantısı aktif!")

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ HATA: BOT_TOKEN çevre değişkeni bulunamadı!")
    elif not REDIS_URL:
        print("❌ HATA: REDIS_URL çevre değişkeni bulunamadı!")
    else:
        bot.run(BOT_TOKEN)
