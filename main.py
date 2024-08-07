import os
import json
import random
import time
from datetime import datetime, timedelta
from instagrapi import Client
import openai
import requests
from dotenv import load_dotenv
import structlog

# structlog yapılandırması
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger(__name__)

def log_with_color(level, message):
    colors = {
        "DEBUG": "\033[94m[DEBUG]\033[0m",
        "INFO": "\033[92m[INFO]\033[0m",
        "WARN": "\033[93m[WARN]\033[0m",
        "ERROR": "\033[91m[ERROR]\033[0m",
        "CRITICAL": "\033[95m[CRITICAL]\033[0m",
    }
    print(f"{colors.get(level, '[INFO]')} {message}")

load_dotenv()
IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def load_json_data():
    with open("isletme-detayli-istem.json", "r", encoding="utf-8") as f:
        business_details = json.load(f)
    with open("sablonlar.json", "r", encoding="utf-8") as f:
        templates = json.load(f)
    with open("icerik-konulari-hizmet-listesi.json", "r", encoding="utf-8") as f:
        resimler_hizmetler = json.load(f)
    return business_details, templates, resimler_hizmetler

def check_internet():
    log_with_color("INFO", "İnternet bağlantısı kontrol ediliyor..")
    try:
        requests.get("http://www.google.com", timeout=5)
        log_with_color("INFO", "İnternet bağlantısı başarılı.")
        return True
    except requests.ConnectionError:
        log_with_color("ERROR", "İnternet bağlantısı yok. Lütfen bağlantınızı kontrol edin.")
        return False

def login_to_instagram(client):
    log_with_color("INFO", "Instagram hesabına giriş yapılıyor..")
    try:
        client.login(IG_USERNAME, IG_PASSWORD)
        log_with_color("INFO", "Giriş başarılı.")
        return True
    except Exception as e:
        log_with_color("ERROR", f"Giriş başarısız: {e}")
        return False

def select_random_service(hizmetler):
    service_name = random.choice(hizmetler)
    log_with_color("INFO", f"Rastgele hizmet seçildi: {service_name}")
    return service_name.lower().replace(" ", "-"), service_name

def generate_content(service, openai_api_key, templates):
    log_with_color("INFO", "Gönderi metni oluşturuluyor")
    openai.api_key = openai_api_key

    service_template = next(
        (t for t in templates["contentTemplates"] if t["name"] == "Hizmet İçerik Şablonu"), None
    )
    service_info = next(
        (c for c in templates["concepts"] if c["name"].lower() == service.lower()), None
    )

    if not service_template or not service_info:
        log_with_color("ERROR", "İçerik oluşturulamadı. Şablon veya hizmet bilgisi eksik.")
        return None

    prompt = f"""
    MedlifeYalova Güzellik Merkezi için '{service}' hizmeti hakkında Instagram gönderisi oluştur.
    İçerik şu bölümlerden oluşmalı:
    1. {service_template['contentText']['title'].replace('[Hizmet Adı]', service_info['name'])}
    2. {service_template['contentText']['description'].replace('[Hizmet Adı]', service_info['name']).replace('[Hizmet Alanı]', service_info['name'])}
    3. {service_template['contentText']['faqTitle']}
    4. Rastgele seçilmiş bir soru-cevap
    5. {service_template['contentText']['contact'].replace('[Hizmet Alanı]', service_info['name'])}
    6. 5 adet ilgili hashtag
    Tüm içerik Türkçe olmalı ve 2000 karakteri geçmemeli.
    """

    try:
        response = openai.Completion.create(
            engine="davinci-002",
            prompt=prompt,
            max_tokens=500,
            n=1,
            stop=None,
            temperature=0.7,
        )
        content = response.choices[0].text.strip()
        log_with_color("INFO", "Gönderi metni oluşturuldu.")
        return content
    except Exception as e:
        log_with_color("ERROR", f"İçerik oluşturma hatası: {e}")
        return None

def generate_story_content(service, openai_api_key, templates):
    log_with_color("INFO", "Story metni oluşturuluyor.")
    openai.api_key = openai_api_key

    service_template = next(
        (t for t in templates["contentTemplates"] if t["name"] == "Hizmet İçerik Şablonu"), None
    )

    if not service_template:
        log_with_color("ERROR", "Story içeriği oluşturulamadı. Şablon eksik.")
        return None

    prompt = f"""
    MedlifeYalova Güzellik Merkezi için '{service}' hizmeti hakkında kısa bir Instagram story metni oluştur.
    Metin şunları içermeli:
    1. {service_template['storySuggestion']['title'].replace('[Başlık Metni]', service)}
    2. {service_template['storySuggestion']['description'].replace('[Hizmet Adı]', service)}
    3. 2-3 ilgili hashtag
    Tüm içerik Türkçe olmalı ve 280 karakteri geçmemeli.
    """

    try:
        response = openai.Completion.create(
            engine="davinci-002",
            prompt=prompt,
            max_tokens=100,
            n=1,
            stop=None,
            temperature=0.7,
        )
        story_content = response.choices[0].text.strip()
        log_with_color("INFO", "Story metni oluşturuldu.")
        return story_content
    except Exception as e:
        log_with_color("ERROR", f"Story içeriği oluşturma hatası: {e}")
        return None

def get_image_path(service_key, resimler):
    image_dir = resimler.get(service_key)
    if not image_dir or not os.path.exists(image_dir):
        log_with_color("ERROR", f"Resim klasörü bulunamadı veya yolunda sorun var: {service_key}")
        return None

    images = [f for f in os.listdir(image_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not images:
        log_with_color("ERROR", f"Resim bulunamadı: {service_key}")
        return None
    return os.path.join(image_dir, random.choice(images))

def check_content_image_match(service_name, content, image_path):
    log_with_color("INFO", "İçerik ve resim eşleşmesi kontrol ediliyor.")
    if service_name.lower() in content.lower() and os.path.exists(image_path):
        log_with_color("INFO", "İçerik ve resim eşleşmesi başarılı.")
        return True
    else:
        log_with_color("ERROR", "İçerik ve resim eşleşmesi başarısız.")
        return False

def humanizer_check(content):
    log_with_color("INFO", "İçerik doğal ve insansı kontrolü yapılıyor.")
    if len(content) > 100 and any(emoji in content for emoji in ["😊", "👍", "💖", "✨"]):
        log_with_color("INFO", "İçerik metni doğal ve insansı.")
        return True
    else:
        log_with_color("ERROR", "İçerik yeterince doğal veya insansı değil.")
        return False

def create_post(client, service_name, content, image_path):
    log_with_color("INFO", "Gönderi oluşturuluyor.")
    try:
        media = client.photo_upload(image_path, caption=content)
        log_with_color("INFO", "Gönderi başarıyla oluşturuldu.")
        return True
    except Exception as e:
        log_with_color("ERROR", f"Gönderi oluşturulamadı: {e}")
        return False

def create_story(client, service_name, image_path):
    log_with_color("INFO", "Story oluşturuluyor.")
    try:
        client.photo_upload_to_story(image_path)
        log_with_color("INFO", "Story başarıyla oluşturuldu.")
        return True
    except Exception as e:
        log_with_color("ERROR", f"Story oluşturulamadı: {e}")
        return False

def main():
    if not check_internet():
        return

    client = Client()
    if not login_to_instagram(client):
        return

    business_details, templates, resimler_hizmetler = load_json_data()
    hizmetler = resimler_hizmetler["Hizmetler"]
    resimler = resimler_hizmetler["resimler"]

    last_post_time = datetime.now() - timedelta(hours=4)
    last_story_time = datetime.now() - timedelta(hours=2)

    while True:
        current_time = datetime.now()

        if current_time - last_post_time >= timedelta(hours=4):
            while True:
                service_key, service_name = select_random_service(hizmetler)
                content = generate_content(service_name, OPENAI_API_KEY, templates)
                if content:
                    break
                else:
                    log_with_color("ERROR", f"{service_name} için içerik oluşturulamadı, yeni hizmet seçiliyor.")
            image_path = get_image_path(service_key, resimler)

            if (
                content
                and image_path
                and check_content_image_match(service_name, content, image_path)
                and humanizer_check(content)
            ):
                if create_post(client, service_name, content, image_path):
                    last_post_time = current_time
                    time.sleep(random.randint(300, 900))  # 5-15 dakika arası rastgele bekleme

        if current_time - last_story_time >= timedelta(hours=2):
            while True:
                service_key, service_name = select_random_service(hizmetler)
                story_content = generate_story_content(service_name, OPENAI_API_KEY, templates)
                if story_content:
                    break
                else:
                    log_with_color("ERROR", f"{service_name} için story oluşturulamadı, yeni hizmet seçiliyor.")
            image_path = get_image_path(service_key, resimler)

            if story_content and image_path:
                if create_story(client, service_name, image_path):
                    last_story_time = current_time
                    time.sleep(random.randint(300, 900))  # 5-15 dakika arası rastgele bekleme

        time.sleep(600)  # 10 dakika bekle

if __name__ == "__main__":
    main()
