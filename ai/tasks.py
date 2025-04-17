from crewai import Task
from ai.agents import create_conversation_coordinator_agent, create_conversation_monitor_agent


def create_conversation_coordinator_task(user_message: str, conversation_history: str, intent: dict) -> Task:
    agent = create_conversation_coordinator_agent()
    monitor = create_conversation_monitor_agent()
    print(conversation_history)
    return Task(
        description=f"""
        Você é um concierge virtual em uma conversa com alguém no portão do condomínio.

        Histórico da conversa:
        {conversation_history}

        Mensagem nova:
        "{user_message}"

        Intenção acumulada até agora:
        {intent}

        Seu trabalho:
        - Verificar se todos os campos estão preenchidos:
          • intent_type
          • visitor_name
          • apartment_number
          • resident_name
        - Se faltar algo, pergunte o que falta.
        - Se estiver completo, apenas confirme.

        Regras:
        - NÃO repita o que já foi dito.
        - NÃO reinicie a conversa.
        - Não peça dados que já estão no intent.
        """,
        # expected_output="""
        # Mensagem para o usuário ou confirmação final.
        # Confirme a ação de forma educada, objetiva e breve.
        # Exemplos de formato desejado:
        # - "Entrega confirmada para Fulano no xxxx. Notificarei o morador."
        # - "Entendido, vou avisar Cicrano no apartamento bla bla bla."
        # Evite repetições desnecessárias, não deseje bom dia ou acrescente floreios.
        # """,
        expected_output=""""
        Responda em formato JSON com os seguintes campos:
        - mensagem: mensagem de resposta clara e objetiva para o usuário, podendo ser a confirmação final. 
        Confirme a ação de forma educada, objetiva e breve. Ex, "Entrega confirmada para Fulano no xxxx. Notificarei o 
        morador"., ou ainda, "Entendido, vou avisar Cicrano no apartamento bla bla bla."
        - dados: objeto com os campos intent_type, visitor_name, apartment_number e resident_name.
        
        Exemplo:
        {
          "mensagem": "Entrega confirmada para Fulano do XXXX.",
          "dados": {
            "intent_type": "entrega",
            "visitor_name": "João",
            "apartment_number": "XXXX",
            "resident_name": "Fulano"
          }
        }
        O campo message é sempre obrigatório, pois você sempre deve ter uma resposta, mesmo que seja uma pergunta para 
        quem está sendo atendido. Se não puder identificar os campos de dados, retorne as chaves com valores vazios. 
        Não use floreios, não repita informações já ditas, apenas informe ou confirme a ação.
        O campo intent_type dentro de dados deve ser preenchido com entrega, visita ou desconhecido, conforme o que 
        você identificar.
        
        Alguns exemplos de campos faltando e possíveis respostas:
        {
          "mensagem": "Informe o que deseja",
          "dados": {
            "intent_type": "",
            "visitor_name": "",
            "apartment_number": "",
            "resident_name": ""
          }
        }
        
        {
          "mensagem": "Por favor, me informe o nome do visitante, o apartamento e o nome do morador que autorizou",
          "dados": {
            "intent_type": "visita",
            "visitor_name": "",
            "apartment_number": "",
            "resident_name": ""
          }
        } 
        
        {
          "mensagem": "Por favor, me informe o seu nome, o apartamento e o nome do morador que vai receber a entrega",
          "dados": {
            "intent_type": "entrega",
            "visitor_name": "",
            "apartment_number": "",
            "resident_name": ""
          }
        }                 
                
        {
          "mensagem": "Por favor, me informe o nome do morador.",
          "dados": {
            "intent_type": "entrega",
            "visitor_name": "Carlos",
            "apartment_number": "301",
            "resident_name": ""
          }
        }
        
        {
          "mensagem": "Por favor, me informe sua intenção",
          "dados": {
            "intent_type": "",
            "visitor_name": "Carlos",
            "apartment_number": "301",
            "resident_name": "Fulano"
          }
        }
        
        {
          "mensagem": "Podes informar o seu nome?",
          "dados": {
            "intent_type": "visita",
            "visitor_name": "",
            "apartment_number": "301",
            "resident_name": "Fulano"
          }
        }      
        
        {
          "mensagem": "Podes informar o número do apartamento?",
          "dados": {
            "intent_type": "visita",
            "visitor_name": "Cicrano",
            "apartment_number": "",
            "resident_name": "Fulano"
          }
        }              
        
        
        """,
        agent=agent
    )
