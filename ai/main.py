from ai.crew import process_user_message_with_coordinator



def process_message(content: str, id: str = "anon") -> dict:
    try:
        return process_user_message_with_coordinator(id=id, message=content)
            
    except Exception as e:
        print(f"Erro ao chamar CrewAI: {e}")
        return "Estou enfrentando alguns problemas técnicos. Por favor, tente novamente mais tarde."
