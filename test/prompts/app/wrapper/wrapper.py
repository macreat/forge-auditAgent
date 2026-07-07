# Puede hablar con cualquier modelo IA local, o API comercial (OpenAI, Anthropic, Opencode) a través de la librería X

class WrapperModels:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = None

    def query_model(prompt):
        """
        Query the model with the given prompt and return the response.
        """
        if self.model_name == "phy3":
            # Implement the logic to query the phy3 model
            pass
        elif self.model_name == "ollama":
            # Implement the logic to query the ollama model
            pass
        else:
            raise ValueError(f"Model {self.model_name} is not supported.")
