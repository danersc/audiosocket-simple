from crewai.tools import tool


@tool("SendMessageTool")
def identify_user_intent(message: str) -> str:
    """
    Extrai intenção do usuário com base na mensagem utilizando um modelo LLM.
    Retorna um JSON no formato esperado por UserIntent.
    """
    return message
