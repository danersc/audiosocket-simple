from crewai import Task
from ai.agents import (create_conversation_coordinator_agent, create_conversation_monitor_agent,
                       identificator_person_agent, identificator_intent_agent, identificator_resident_apartment_agent)


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
          • interlocutor_name
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
        - dados: objeto com os campos intent_type, interlocutor_name, apartment_number e resident_name.
        
        Exemplo:
        {
          "mensagem": "Entrega confirmada para Fulano do XXXX.",
          "dados": {
            "intent_type": "entrega",
            "interlocutor_name": "João",
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
            "interlocutor_name": "",
            "apartment_number": "",
            "resident_name": ""
          }
        }
        
        {
          "mensagem": "Por favor, me informe o nome do visitante, o apartamento e o nome do morador que autorizou",
          "dados": {
            "intent_type": "visita",
            "interlocutor_name": "",
            "apartment_number": "",
            "resident_name": ""
          }
        } 
        
        {
          "mensagem": "Por favor, me informe o seu nome, o apartamento e o nome do morador que vai receber a entrega",
          "dados": {
            "intent_type": "entrega",
            "interlocutor_name": "",
            "apartment_number": "",
            "resident_name": ""
          }
        }                 
                
        {
          "mensagem": "Por favor, me informe o nome do morador.",
          "dados": {
            "intent_type": "entrega",
            "interlocutor_name": "Carlos",
            "apartment_number": "301",
            "resident_name": ""
          }
        }
        
        {
          "mensagem": "Por favor, me informe sua intenção",
          "dados": {
            "intent_type": "",
            "interlocutor_name": "Carlos",
            "apartment_number": "301",
            "resident_name": "Fulano"
          }
        }
        
        {
          "mensagem": "Podes informar o seu nome?",
          "dados": {
            "intent_type": "visita",
            "interlocutor_name": "",
            "apartment_number": "301",
            "resident_name": "Fulano"
          }
        }      
        
        {
          "mensagem": "Podes informar o número do apartamento?",
          "dados": {
            "intent_type": "visita",
            "interlocutor_name": "Cicrano",
            "apartment_number": "",
            "resident_name": "Fulano"
          }
        }              
        
        
        """,
        agent=agent
    )


def conversation_extractor_name_task(user_message: str, conversation_history: str, intent: dict) -> Task:
    agent = identificator_person_agent()
    print(conversation_history)
    return Task(
        description=f"""
        Você é o concierge inicial virtual do condomínio em uma conversa com alguém no portão do condomínio.

        Histórico da conversa:
        {conversation_history}

        Mensagem nova:
        "{user_message}"

        Intenção acumulada até agora:
        {intent}

        Seu trabalho:
        - Verificar se o campo interlocutor_name está preenchido:
          • interlocutor_name
        - Se não souber o nome da pessoa, pergunte
        - Se estiver completo, com um nome legível e aceitável, apenas confirme.

        Regras:
        - NÃO repita o que já foi dito.
        - NÃO reinicie a conversa.
        - Não peça dados que já estão no identificados.
        """,
        expected_output=""""
        Responda em formato JSON onde o campo interlocutor_name deve estar preenchido com o nome do visitante. 
        O campo de intent_type também deve estar preenchido pois já perguntamos isso ao interlocutor. Os outros
        campos (apartment_number e resident_name) dentro de dados serão preenchidos pelos outros concierges. 
        Exemplo de mensagem quando ainda não foi identificado o nome:
        {
          "mensagem": "Por favor, me informe o seu nome",
          "dados": {
            "intent_type": "",
            "interlocutor_name": "",
            "apartment_number": "",
            "resident_name": ""
          }
        }
        
        Exemplo de mensagem quando foi identificado o nome:
        {
          "mensagem": "Obrigado Fulano, aguarde um instante",
          "dados": {
            "intent_type": "",
            "interlocutor_name": "Fulano",
            "apartment_number": "",
            "resident_name": ""
          }
        }
        """,
        agent=agent
    )


def conversation_extractor_intent_task(user_message: str, conversation_history: str, intent: dict) -> Task:
    agent = identificator_intent_agent()
    print(conversation_history)
    return Task(
        description=f"""
        Você é o concierge virtual primário do condomínio em uma conversa com alguém no portão do condomínio.

        Histórico da conversa:
        {conversation_history}

        Mensagem nova:
        "{user_message}"

        Intenção acumulada até agora:
        {intent}

        Seu trabalho:
        - Verificar se o campo intent_type está preenchido:
          • intent_type
        - Se não souber a intenção da pessoa, pergunte.
        - Se estiver completo, com a intenção identificada entre entrega e visita, apenas confirme.

        Regras:
        - NÃO repita o que já foi dito.
        - NÃO reinicie a conversa.
        - Não peça dados que já estão no identificados.
        """,
        expected_output=""""
        Responda em formato JSON onde o campo intent_type deve estar preenchido com a intenção do visitante. Os outros
        campos dentro de dados serão preenchidos pelos outros concierges.
        Mesmo que o usuário diga outras informações, ignore informações como o apartamento e o nome do morador, 
        apenas retorne a intenção (intent_type).

        Exemplo de mensagem quando ainda não foi identificadoa a intenção:
        {
          "mensagem": "Por favor, me informe sua intenção, se visita ou entrega",
          "dados": {
            "intent_type": "",
            "interlocutor_name": "Fulano",
            "apartment_number": "",
            "resident_name": ""
          }
        }

        Exemplo de mensagem quando foi identificada a intenção:
        {
          "mensagem": "Obrigado Fulano, aguarde um instante",
          "dados": {
            "intent_type": "visita",
            "interlocutor_name": "Fulano",
            "apartment_number": "",
            "resident_name": ""
          }
        }
        """,
        agent=agent
    )


def conversation_extractor_resident_apartment_task(user_message: str, conversation_history: str, intent: dict) -> Task:
    agent = identificator_resident_apartment_agent()
    print(conversation_history)
    return Task(
        description=f"""
        Você é o concierge virtual terciário em uma conversa com alguém no portão do condomínio.

        Histórico da conversa:
        {conversation_history}

        Mensagem nova:
        "{user_message}"

        Intenção acumulada até agora:
        {intent}

        Seu trabalho:
        - Verificar se os campos apartment_number e resident_name estão preenchidos:
          • apartment_number
          • resident_name
        - Se não souber o apartamento ou o morador, pergunte
        - Se estiver completo, com o apartamento e o nome do morador, apenas confirme.

        Regras:
        - NÃO repita o que já foi dito.
        - NÃO reinicie a conversa.
        - Não peça dados que já estão no identificados.
        """,
        expected_output=""""
        Responda em formato JSON onde os campos apartment_number e resident_name devem estar preenchidos com o
        número do apartamento e nome do morador. Os outros campos serão preenchidos pelos outros concierges.

        Exemplo de mensagem quando ainda não foi identificado o apartamento ou o morador:
        {
          "mensagem": "Por favor, me informe sua para qual apartamento e o nome do morador",
          "dados": {
            "intent_type": "visita",
            "interlocutor_name": "Fulano",
            "apartment_number": "",
            "resident_name": ""
          }
        }

        Exemplo de mensagem quando foi identificado o apartamento e o morador:
        {
          "mensagem": "Obrigado Fulano, aguarde um instante",
          "dados": {
            "intent_type": "visita",
            "interlocutor_name": "Fulano",
            "apartment_number": "501",
            "resident_name": "Cicrano"
          }
        }
        """,
        agent=agent
    )
