import csv, json, os, re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.parse import urlencode

URL='https://www.ifood.com.br/delivery/maringa-pr/baudelaire-cookies-zona-04/c7e645b4-74ed-4cc2-926a-c74f3e7a662c'
ROOT=Path(__file__).resolve().parent
STATE=ROOT/'data'/'status.json'; LOG=ROOT/'data'/'historico.csv'
STAMP=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds')

def status_of(text, code):
    if code != 200: return 'INDETERMINADO',f'HTTP {code}; o iFood não permitiu verificar'
    text=re.sub(r'\s+',' ',text.lower())
    if any(x in text for x in ('captcha','access denied','verifique se você é humano','informe seu endereço')):
        return 'INDETERMINADO','Desafio de segurança ou endereço de entrega necessário'
    if re.search(r'loja fechada|loja indisponível|não está aceitando pedidos|fora do horário de funcionamento',text):
        return 'FECHADA','Mensagem de loja fechada identificada (não confirmada no checkout)'
    if re.search(r'loja aberta|aceitando pedidos agora',text):
        return 'POSSIVEL_ABERTURA','Mensagem sugerindo abertura; confirmação de compra indisponível'
    return 'INDETERMINADO','Nenhum sinal confiável de abertura ou fechamento'

def telegram(msg):
    token=os.environ.get('TELEGRAM_BOT_TOKEN',''); chat=os.environ.get('TELEGRAM_CHAT_ID','')
    if not token or not chat: return
    payload=urlencode({'chat_id':chat,'text':msg,'disable_web_page_preview':'true'}).encode()
    req=Request(f'https://api.telegram.org/bot{token}/sendMessage',data=payload)
    with urlopen(req,timeout=15) as resp: resp.read()

def main():
    previous={}
    if STATE.exists():
        try: previous=json.loads(STATE.read_text(encoding='utf-8'))
        except (ValueError,OSError): pass
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
            page=browser.new_page(locale='pt-BR',timezone_id='America/Sao_Paulo')
            response=page.goto(URL,wait_until='domcontentloaded',timeout=30000)
            page.wait_for_timeout(3000)
            code=response.status if response else 0
            try: body=page.locator('body').inner_text(timeout=7000)
            except Exception: body=''
            state,detail=status_of(body,code)
            browser.close()
    except Exception as exc:
        state,detail='INDETERMINADO',f'Erro ao verificar ({type(exc).__name__})'
    data={'checked_at':STAMP,'status':state,'details':detail,'store_url':URL,
          'last_possible_open_at':previous.get('last_possible_open_at')}
    new_open=(state=='POSSIVEL_ABERTURA' and previous.get('status') not in ('POSSIVEL_ABERTURA',None))
    if new_open:
        data['last_possible_open_at']=STAMP
        try: telegram('🍪 POSSÍVEL abertura da Baudelaire em Maringá! Confira no iFood:\n'+URL+'\n⚠️ Disponibilidade ainda não confirmada.')
        except Exception as exc: print('Falha no Telegram:',type(exc).__name__)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fresh=not LOG.exists()
    with LOG.open('a',encoding='utf-8',newline='') as f:
        writer=csv.writer(f)
        if fresh: writer.writerow(['data_hora_brasilia','status','detalhes'])
        writer.writerow([STAMP,state,detail])
    # Cap CSV at 2000 entries
    with LOG.open(encoding='utf-8',newline='') as f: rows=list(csv.reader(f))
    if len(rows)>2001:
        with LOG.open('w',encoding='utf-8',newline='') as f: csv.writer(f).writerows([rows[0],*rows[-2000:]])
    print(state,detail)

if __name__=='__main__': main()
