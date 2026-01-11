#!/usr/bin/env python3
"""
Workflow Manager - Coleta informações via Telegram e inicia produção
Roda dentro do GitHub Actions, sem necessidade de servidor externo
FUNCIONALIDADE: Permite cancelar workflow via comando /cancel
"""

import os
import json
import time
import requests
import sys
from datetime import datetime
from pathlib import Path

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Directories
PRODUCTIONS_DIR = Path('productions')
PRODUCTIONS_DIR.mkdir(exist_ok=True)

# Cancel flag file
CANCEL_FLAG_FILE = Path('productions/cancel_flag.json')

class WorkflowCancelled(Exception):
    """Exception raised when workflow is cancelled by user"""
    pass

class TelegramCollector:
    """Coleta informações via Telegram de forma interativa"""
    
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        self.chat_id = TELEGRAM_CHAT_ID
        self.update_offset = self._get_last_update_id()
        self.cancelled = False
    
    def _get_last_update_id(self):
        """Obtém o último update_id para não processar mensagens antigas"""
        try:
            url = f"{self.base_url}/getUpdates"
            response = requests.get(url, params={'offset': -1}, timeout=5)
            result = response.json()
            
            if result.get('ok') and result.get('result'):
                return result['result'][0]['update_id'] + 1
            return 0
        except:
            return 0
    
    def send_message(self, text, reply_markup=None):
        """Envia mensagem para o usuário"""
        url = f"{self.base_url}/sendMessage"
        data = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        
        try:
            response = requests.post(url, json=data, timeout=10)
            result = response.json()
            if result.get('ok'):
                print(f"✅ Mensagem enviada")
                return True
            else:
                print(f"⚠️ Erro ao enviar: {result}")
                return False
        except Exception as e:
            print(f"❌ Erro: {e}")
            return False
    
    def check_for_cancel(self):
        """Verifica se usuário enviou comando /cancel"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                'offset': self.update_offset,
                'timeout': 0
            }
            
            response = requests.get(url, params=params, timeout=5)
            result = response.json()
            
            if not result.get('ok'):
                return False
            
            updates = result.get('result', [])
            
            for update in updates:
                self.update_offset = update['update_id'] + 1
                
                if 'message' in update:
                    message = update['message']
                    
                    # Verificar se é do chat correto
                    if str(message['chat']['id']) != str(self.chat_id):
                        continue
                    
                    # Verificar comando de cancelamento
                    text = message.get('text', '').strip().lower()
                    
                    if text in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                        print("🛑 Comando de cancelamento recebido!")
                        self.cancelled = True
                        
                        # Criar arquivo de flag
                        cancel_data = {
                            'cancelled': True,
                            'timestamp': datetime.now().isoformat(),
                            'reason': 'User requested cancellation'
                        }
                        
                        with open(CANCEL_FLAG_FILE, 'w') as f:
                            json.dump(cancel_data, f, indent=2)
                        
                        self.send_message(
                            "🛑 <b>WORKFLOW CANCELADO</b>\n\n"
                            "A produção foi cancelada com sucesso.\n"
                            "O workflow será encerrado."
                        )
                        
                        return True
            
            return False
            
        except Exception as e:
            print(f"⚠️ Erro ao verificar cancelamento: {e}")
            return False
    
    def wait_for_message(self, timeout=600, check_cancel_interval=5):
        """Aguarda mensagem do usuário (com verificação de cancelamento)"""
        print(f"⏳ Aguardando resposta (timeout: {timeout}s)...")
        
        start_time = time.time()
        last_reminder = 0
        last_cancel_check = 0
        
        while time.time() - start_time < timeout:
            # Verificar cancelamento a cada 5 segundos
            elapsed = time.time() - start_time
            if elapsed - last_cancel_check >= check_cancel_interval:
                if self.check_for_cancel():
                    raise WorkflowCancelled("Workflow cancelled by user")
                last_cancel_check = elapsed
            
            # Enviar lembrete a cada 2 minutos
            if int(elapsed) // 120 > last_reminder:
                remaining = int((timeout - elapsed) / 60)
                self.send_message(
                    f"⏰ Ainda aguardando sua resposta...\n"
                    f"⏱️ {remaining} minutos restantes\n\n"
                    f"💡 Use /cancel para cancelar a produção"
                )
                last_reminder = int(elapsed) // 120
            
            # Buscar updates
            try:
                url = f"{self.base_url}/getUpdates"
                params = {
                    'offset': self.update_offset,
                    'timeout': 10
                }
                
                response = requests.get(url, params=params, timeout=15)
                result = response.json()
                
                if not result.get('ok'):
                    time.sleep(3)
                    continue
                
                updates = result.get('result', [])
                
                for update in updates:
                    self.update_offset = update['update_id'] + 1
                    
                    if 'message' in update:
                        message = update['message']
                        
                        # Verificar se é do chat correto
                        if str(message['chat']['id']) != str(self.chat_id):
                            continue
                        
                        # Pegar texto
                        text = message.get('text', '').strip()
                        
                        # Verificar se é comando de cancelamento
                        if text.lower() in ['/cancel', '/cancelar', 'cancel', 'cancelar']:
                            self.cancelled = True
                            cancel_data = {
                                'cancelled': True,
                                'timestamp': datetime.now().isoformat(),
                                'reason': 'User requested cancellation'
                            }
                            with open(CANCEL_FLAG_FILE, 'w') as f:
                                json.dump(cancel_data, f, indent=2)
                            
                            self.send_message(
                                "🛑 <b>WORKFLOW CANCELADO</b>\n\n"
                                "A produção foi cancelada com sucesso."
                            )
                            raise WorkflowCancelled("Workflow cancelled by user")
                        
                        if text:
                            print(f"✅ Resposta recebida: {text[:50]}...")
                            return text
            
            except WorkflowCancelled:
                raise
            except Exception as e:
                print(f"⚠️ Erro ao buscar updates: {e}")
                time.sleep(5)
        
        print("⏰ Timeout - sem resposta")
        return None
    
    def collect_video_info(self):
        """Coleta título, descrição e roteiro via Telegram"""
        print("\n" + "="*60)
        print("📱 COLETANDO INFORMAÇÕES VIA TELEGRAM")
        print("="*60)
        
        try:
            # Limpar flag de cancelamento anterior
            if CANCEL_FLAG_FILE.exists():
                CANCEL_FLAG_FILE.unlink()
            
            # Mensagem inicial
            self.send_message(
                "🎬 <b>Produção Diária de Vídeo WWII</b>\n\n"
                "Vamos criar um novo vídeo histórico!\n\n"
                "Responda às próximas perguntas para começar.\n"
                "⏱️ Você tem 10 minutos para cada resposta.\n\n"
                "🛑 Use <b>/cancel</b> a qualquer momento para cancelar"
            )
            
            time.sleep(2)
            
            # Coletar TÍTULO
            self.send_message(
                "1️⃣ <b>TÍTULO DO VÍDEO</b>\n\n"
                "Envie o título do seu vídeo sobre WWII.\n\n"
                "<i>Exemplo: The Forgotten Heroes of D-Day</i>\n\n"
                "💡 Ou envie /cancel para cancelar"
            )
            
            titulo = self.wait_for_message(timeout=600)
            
            if not titulo:
                self.send_message("❌ Tempo esgotado. Produção cancelada.")
                return None
            
            self.send_message(f"✅ Título recebido!\n\n<b>{titulo}</b>")
            time.sleep(2)
            
            # Coletar DESCRIÇÃO
            self.send_message(
                "2️⃣ <b>DESCRIÇÃO DO VÍDEO</b>\n\n"
                "Envie a descrição que aparecerá no YouTube.\n\n"
                "<i>Pode ser de 2 a 3 parágrafos explicando o conteúdo.</i>\n\n"
                "💡 Ou envie /cancel para cancelar"
            )
            
            descricao = self.wait_for_message(timeout=600)
            
            if not descricao:
                self.send_message("❌ Tempo esgotado. Produção cancelada.")
                return None
            
            self.send_message(
                f"✅ Descrição recebida!\n\n"
                f"<i>{descricao[:100]}...</i>"
            )
            time.sleep(2)
            
            # Coletar TAGS
            self.send_message(
                "3️⃣ <b>TAGS DO VÍDEO</b>\n\n"
                "Envie as tags separadas por vírgula.\n\n"
                "<i>Exemplo: WWII, D-Day, History, Documentary, Normandy</i>\n\n"
                "💡 Ou envie /cancel para cancelar"
            )
            
            tags_text = self.wait_for_message(timeout=600)
            
            if not tags_text:
                self.send_message("❌ Tempo esgotado. Produção cancelada.")
                return None
            
            tags = [tag.strip() for tag in tags_text.split(',')]
            self.send_message(f"✅ Tags recebidas: {len(tags)} tags")
            time.sleep(2)
            
            # Coletar ROTEIRO
            self.send_message(
                "4️⃣ <b>ROTEIRO DE NARRAÇÃO</b>\n\n"
                "Agora envie o roteiro completo que será narrado no vídeo.\n\n"
                "📝 <b>Dicas:</b>\n"
                "• Escreva em inglês\n"
                "• Use frases claras para narração\n"
                "• Conte uma história envolvente\n"
                "• Não mencione elementos visuais\n\n"
                "⏱️ Você tem 15 minutos para enviar.\n\n"
                "💡 Ou envie /cancel para cancelar"
            )
            
            roteiro = self.wait_for_message(timeout=900)  # 15 minutos
            
            if not roteiro:
                self.send_message("❌ Tempo esgotado. Produção cancelada.")
                return None
            
            palavra_count = len(roteiro.split())
            tempo_estimado = palavra_count / 150  # ~150 palavras por minuto
            
            self.send_message(
                f"✅ <b>Roteiro recebido!</b>\n\n"
                f"📊 Estatísticas:\n"
                f"• Palavras: {palavra_count}\n"
                f"• Duração estimada: {tempo_estimado:.1f} minutos\n"
                f"• Segmentos (~30s): {int(tempo_estimado * 2)}\n\n"
                f"🎬 Iniciando produção...\n\n"
                f"🛑 Você ainda pode cancelar usando /cancel"
            )
            
            # Salvar dados coletados
            video_data = {
                'video_id': f"video_{int(time.time())}",
                'timestamp': datetime.now().isoformat(),
                'title': titulo,
                'description': descricao,
                'tags': tags,
                'script': roteiro,
                'status': 'collected',
                'word_count': palavra_count,
                'estimated_duration': tempo_estimado
            }
            
            # Salvar em arquivo
            production_file = PRODUCTIONS_DIR / f"{video_data['video_id']}.json"
            with open(production_file, 'w', encoding='utf-8') as f:
                json.dump(video_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n✅ Informações coletadas e salvas: {production_file}")
            
            return video_data
        
        except WorkflowCancelled:
            print("🛑 Workflow cancelado pelo usuário")
            return None

def main():
    """Função principal do workflow"""
    print("="*60)
    print("🎬 WORKFLOW MANAGER - WWII Video Production")
    print("="*60)
    print(f"⏰ Iniciado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Verificar variáveis de ambiente
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN não configurado!")
        return 1
    
    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID não configurado!")
        return 1
    
    print("✅ Variáveis de ambiente OK")
    print()
    
    try:
        # Coletar informações via Telegram
        collector = TelegramCollector()
        video_data = collector.collect_video_info()
        
        if not video_data:
            print("\n❌ Falha ao coletar informações. Workflow cancelado.")
            return 1
        
        print("\n✅ Informações coletadas com sucesso!")
        print(f"🎯 Título: {video_data['title']}")
        print(f"📝 Roteiro: {video_data['word_count']} palavras")
        print(f"⏱️ Duração estimada: {video_data['estimated_duration']:.1f} min")
        print()
        
        # Agora importar e executar a produção do vídeo
        print("="*60)
        print("🎥 INICIANDO PRODUÇÃO DO VÍDEO")
        print("="*60)
        print()
        
        # Importar módulo de criação de vídeo
        import create_video
        
        # Executar produção (que também pode ser cancelada)
        success = create_video.run_production(video_data, collector)
        
        if success:
            print("\n🎉 PRODUÇÃO CONCLUÍDA COM SUCESSO!")
            return 0
        else:
            print("\n❌ Falha na produção do vídeo")
            return 1
    
    except WorkflowCancelled:
        print("\n🛑 WORKFLOW CANCELADO PELO USUÁRIO")
        return 2  # Exit code 2 para cancelamento
    
    except Exception as e:
        print(f"\n❌ Erro durante a produção: {e}")
        import traceback
        traceback.print_exc()
        
        # Notificar erro via Telegram
        try:
            collector = TelegramCollector()
            collector.send_message(
                f"❌ <b>Erro na Produção</b>\n\n"
                f"Ocorreu um erro durante a criação do vídeo:\n\n"
                f"<code>{str(e)}</code>\n\n"
                f"Verifique os logs no GitHub Actions."
            )
        except:
            pass
        
        return 1

if __name__ == '__main__':
    sys.exit(main())
