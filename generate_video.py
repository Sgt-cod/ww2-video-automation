import os
import json
import random
import re
import asyncio
from datetime import datetime
import requests
import edge_tts
from moviepy.editor import *
from google import generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CONFIG_FILE = 'config.json'
VIDEOS_DIR = 'videos'
ASSETS_DIR = 'assets'
VIDEO_TYPE = os.environ.get('VIDEO_TYPE', 'short')

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
YOUTUBE_CREDENTIALS = os.environ.get('YOUTUBE_CREDENTIALS')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

def gerar_roteiro(duracao_alvo, tema):
    """Gera roteiro motivacional filosófico"""
    if duracao_alvo == 'short':
        palavras_alvo = 120
        tempo = '30-60 segundos'
    else:
        palavras_alvo = config.get('duracao_minutos', 10) * 150
        tempo = f"{config.get('duracao_minutos', 10)} minutos"
    
    prompt = f"""Crie um roteiro motivacional e filosófico sobre: {tema}

IMPORTANTE:
- Você é um OBSERVADOR EXTERNO sábio e filosófico
- Fale em TERCEIRA PESSOA sobre a humanidade e a vida
- Tom: reflexivo, inspirador, profundo, motivacional
- Use frases como: "As pessoas...", "O ser humano...", "A vida...", "Quando alguém..."
- Filosofe sobre: superação, força de vontade, coragem, propósito, crescimento pessoal
- Faça o espectador REFLETIR sobre sua própria jornada
- Use metáforas e analogias poderosas
- Inspire ação e transformação
- Para SHORTS: seja direto, impactante, uma mensagem poderosa
- Para LONGS: desenvolva o tema com profundidade, conte histórias, use exemplos
- {tempo} de duração, aproximadamente {palavras_alvo} palavras
- Texto corrido para narração
- SEM formatação, asteriscos ou marcadores
- SEM emojis
- Comece de forma envolvente (ex: "Existe um momento na vida de toda pessoa...", "A força não vem do que você consegue fazer...")
- Finalize com reflexão profunda ou chamada para ação interior

Escreva APENAS o roteiro de narração."""
    
    response = model.generate_content(prompt)
    texto = response.text
    
    # Limpeza do texto
    texto = re.sub(r'\*+', '', texto)
    texto = re.sub(r'#+\s', '', texto)
    texto = re.sub(r'^-\s', '', texto, flags=re.MULTILINE)
    texto = texto.replace('*', '').replace('#', '').replace('_', '').strip()
    
    return texto

async def criar_audio_async(texto, output_file):
    """Cria áudio com Edge TTS (async)"""
    voz = config.get('voz', 'pt-BR-AntonioNeural')
    
    for tentativa in range(3):
        try:
            communicate = edge_tts.Communicate(texto, voz, rate="+0%", pitch="+0Hz")
            await asyncio.wait_for(communicate.save(output_file), timeout=120)
            print(f"✅ Edge TTS (tent {tentativa + 1})")
            return
        except asyncio.TimeoutError:
            print(f"⏱️ Timeout {tentativa + 1}")
            if tentativa < 2:
                await asyncio.sleep(10)
        except Exception as e:
            print(f"⚠️ Erro {tentativa + 1}: {e}")
            if tentativa < 2:
                await asyncio.sleep(10)
    
    raise Exception("Edge TTS falhou")

def criar_audio(texto, output_file):
    """Cria áudio com Edge TTS ou gTTS (fallback)"""
    print("🎙️ Criando narração...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(criar_audio_async(texto, output_file))
        loop.close()
        
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            print(f"✅ Edge TTS: {os.path.getsize(output_file)} bytes")
            return output_file
    except Exception as e:
        print(f"❌ Edge TTS: {e}")
        print("🔄 Fallback gTTS...")
        from gtts import gTTS
        tts = gTTS(text=texto, lang='pt-br', slow=False)
        tts.save(output_file)
        print("⚠️ gTTS")
        return output_file

def buscar_videos_local(quantidade=1):
    """Busca vídeos na pasta genericas"""
    
    pasta_videos = f'{ASSETS_DIR}/genericas'
    videos = []
    
    try:
        if os.path.exists(pasta_videos):
            arquivos = [f for f in os.listdir(pasta_videos) 
                       if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
            
            if arquivos:
                random.shuffle(arquivos)
                
                for arquivo in arquivos[:quantidade]:
                    caminho_completo = os.path.join(pasta_videos, arquivo)
                    if os.path.exists(caminho_completo):
                        videos.append(caminho_completo)
                
                if videos:
                    print(f"   ✅ Banco LOCAL: {len(videos)} vídeo(s)")
                    return videos
            else:
                print(f"   ⚠️ Pasta 'genericas' está vazia")
        else:
            print(f"   ⚠️ Pasta 'genericas' não existe: {pasta_videos}")
    except Exception as e:
        print(f"   ⚠️ Erro ao buscar vídeos: {e}")
    
    return videos

def criar_video_short(audio_path, videos_local, output_file, duracao):
    """Cria SHORT com vídeos do banco local"""
    print(f"📹 Criando short com {len(videos_local)} vídeos para {duracao:.1f}s")
    
    clips = []
    
    # Se tiver poucos vídeos, repete
    if len(videos_local) < 3:
        videos_local = videos_local * 3
    
    duracao_por_video = duracao / len(videos_local)
    
    for i, video_path in enumerate(videos_local):
        try:
            vclip = VideoFileClip(video_path, audio=False)
            
            # Ajustar para formato vertical (9:16)
            ratio = 9/16
            if vclip.w / vclip.h > ratio:
                # Vídeo mais largo - cortar largura
                new_w = int(vclip.h * ratio)
                vclip = vclip.crop(x_center=vclip.w/2, width=new_w, height=vclip.h)
            else:
                # Vídeo mais alto - cortar altura
                new_h = int(vclip.w / ratio)
                vclip = vclip.crop(y_center=vclip.h/2, width=vclip.w, height=new_h)
            
            # Redimensionar para 1080x1920
            vclip = vclip.resize((1080, 1920))
            
            # Definir duração
            vclip = vclip.set_duration(min(duracao_por_video, vclip.duration))
            
            # Crossfade suave
            if i > 0:
                vclip = vclip.crossfadein(0.3)
            
            clips.append(vclip)
            print(f"   ✅ Vídeo {i+1}/{len(videos_local)} adicionado")
            
        except Exception as e:
            print(f"   ⚠️ Erro no vídeo {i}: {e}")
            continue
    
    if not clips:
        print("❌ Nenhum clip criado!")
        return None
    
    # Concatenar vídeos
    video = concatenate_videoclips(clips, method="compose")
    video = video.set_duration(duracao)
    
    # Adicionar áudio
    audio = AudioFileClip(audio_path)
    video = video.set_audio(audio)
    
    # Renderizar
    video.write_videofile(
        output_file, 
        fps=30, 
        codec='libx264', 
        audio_codec='aac', 
        preset='medium', 
        bitrate='8000k'
    )
    
    return output_file

def criar_video_long(audio_path, videos_local, output_file, duracao):
    """Cria vídeo LONGO com vídeos do banco local"""
    print(f"📹 Criando long com {len(videos_local)} vídeos para {duracao:.1f}s")
    
    clips = []
    duracao_por_video = duracao / len(videos_local)
    
    for i, video_path in enumerate(videos_local):
        try:
            vclip = VideoFileClip(video_path, audio=False)
            
            # Ajustar para formato horizontal (16:9)
            vclip = vclip.resize(height=1080)
            
            if vclip.w < 1920:
                vclip = vclip.resize(width=1920)
            
            # Centralizar e cortar
            vclip = vclip.crop(
                x_center=vclip.w/2, 
                y_center=vclip.h/2, 
                width=1920, 
                height=1080
            )
            
            # Definir duração
            vclip = vclip.set_duration(min(duracao_por_video, vclip.duration))
            
            # Crossfade suave
            if i > 0:
                vclip = vclip.crossfadein(0.5)
            
            clips.append(vclip)
            print(f"   ✅ Vídeo {i+1}/{len(videos_local)} adicionado")
            
        except Exception as e:
            print(f"   ⚠️ Erro no vídeo {i}: {e}")
            continue
    
    if not clips:
        print("❌ Nenhum clip criado!")
        return None
    
    # Concatenar vídeos
    video = concatenate_videoclips(clips, method="compose")
    video = video.set_duration(duracao)
    
    # Adicionar áudio
    audio = AudioFileClip(audio_path)
    video = video.set_audio(audio)
    
    # Renderizar
    video.write_videofile(
        output_file, 
        fps=24, 
        codec='libx264', 
        audio_codec='aac', 
        preset='medium', 
        bitrate='5000k'
    )
    
    return output_file

def fazer_upload_youtube(video_path, titulo, descricao, tags):
    """Faz upload do vídeo para o YouTube"""
    try:
        creds_dict = json.loads(YOUTUBE_CREDENTIALS)
        credentials = Credentials.from_authorized_user_info(creds_dict)
        youtube = build('youtube', 'v3', credentials=credentials)
        
        body = {
            'snippet': {
                'title': titulo,
                'description': descricao,
                'tags': tags,
                'categoryId': '22'  # People & Blogs (melhor para motivacional)
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False
            }
        }
        
        media = MediaFileUpload(video_path, resumable=True)
        request = youtube.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )
        response = request.execute()
        
        return response['id']
    except Exception as e:
        print(f"❌ Erro upload: {e}")
        raise

def main():
    print(f"{'📱' if VIDEO_TYPE == 'short' else '🎬'} Iniciando Bot Motivacional...")
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(f'{ASSETS_DIR}/genericas', exist_ok=True)

    # Escolher tema aleatório
    tema = random.choice(config.get('temas', ['superação pessoal']))
    print(f"🎯 Tema: {tema}")

    # Gerar roteiro
    print("✍️ Gerando roteiro motivacional...")
    roteiro = gerar_roteiro(VIDEO_TYPE, tema)
    
    print(f"\n📝 Roteiro gerado ({len(roteiro)} caracteres)")
    print(f"Preview: {roteiro[:150]}...\n")

    # Criar áudio
    audio_path = f'{ASSETS_DIR}/audio.mp3'
    criar_audio(roteiro, audio_path)

    audio_clip = AudioFileClip(audio_path)
    duracao = audio_clip.duration
    audio_clip.close()

    print(f"⏱️ Duração: {duracao:.1f}s")

    # Buscar vídeos locais
    print("🎬 Buscando vídeos no banco local...")
    
    if VIDEO_TYPE == 'short':
        quantidade = 6  # 6 vídeos para short
    else:
        quantidade = max(10, int(duracao / 12))  # ~12s por vídeo
    
    videos = buscar_videos_local(quantidade)
    
    if not videos:
        print("❌ ERRO: Nenhum vídeo encontrado na pasta 'genericas'!")
        print("Por favor, adicione vídeos (.mp4, .mov, .avi, .mkv) em: assets/genericas/")
        return
    
    print(f"✅ {len(videos)} vídeos encontrados")

    # Montar vídeo
    print("\n🎥 Montando vídeo...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    video_path = f'{VIDEOS_DIR}/{VIDEO_TYPE}_{timestamp}.mp4'

    if VIDEO_TYPE == 'short':
        resultado = criar_video_short(audio_path, videos, video_path, duracao)
    else:
        resultado = criar_video_long(audio_path, videos, video_path, duracao)

    if not resultado:
        print("❌ Erro ao criar vídeo")
        return

    # Preparar metadados
    titulo = tema[:60] if len(tema) <= 60 else tema[:57] + '...'
    
    if VIDEO_TYPE == 'short':
        titulo += ' #shorts'

    descricao = f"""{roteiro[:300]}...

🔔 Inscreva-se para mais reflexões e motivação!

#motivacao #superacao #reflexao #filosofia #inspiracao"""
    
    if VIDEO_TYPE == 'short':
        descricao += ' #shorts'

    tags = ['motivacao', 'superacao', 'reflexao', 'filosofia', 'inspiracao', 'autoajuda', 'desenvolvimento pessoal']
    if VIDEO_TYPE == 'short':
        tags.append('shorts')

    # Upload
    print("\n📤 Fazendo upload para o YouTube...")
    try:
        video_id = fazer_upload_youtube(video_path, titulo, descricao, tags)
        
        url = f'https://youtube.com/{"shorts" if VIDEO_TYPE == "short" else "watch?v="}{video_id}'
        
        # Log
        log_entry = {
            'data': datetime.now().isoformat(),
            'tipo': VIDEO_TYPE,
            'tema': tema,
            'titulo': titulo,
            'duracao': duracao,
            'video_id': video_id,
            'url': url
        }
        
        log_file = 'videos_gerados.json'
        logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Vídeo publicado com sucesso!")
        print(f"🔗 {url}")
        
        # Limpar arquivos temporários (mantém vídeos em genericas)
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except:
            pass
            
    except Exception as e:
        print(f"\n❌ Erro no upload: {e}")

if __name__ == '__main__':
    main()
