from pathlib import Path
from datetime import datetime
import argparse

from PersonaVLM import PersonaVLMAgent


class UserConfig:
    """Stores user-specific configuration for the agent."""
    def __init__(self, user_name="Anddy"):
        self.USER_NAME = user_name
        self.DATA_STORAGE_PATH = Path(f"./output/{self.USER_NAME}")
        self.DATA_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
        
        # --- Optional Configurations ---
        self.PROFILE = {
            "requirements or expectations": "response concise and accurate",
            "preferences": "lovely pet"
        }


def chat(args):
    user_config = UserConfig()
    agent = PersonaVLMAgent.PersonaVLM(
        user_config, 
        force_retrieve=args.force_retrieve, 
        reasoning_mode=args.reasoning_mode
    )

    print("--- Agent Chat Started ---")
    print("-" * 30)
    while True:
        try:
            user_input = input("Current User Input: ")
            if user_input.lower() in ['exit', 'quit']:
                break

            if not user_input.strip():
                continue
            query_parts = user_input.split()
            image_paths = [part for part in query_parts if part.lower().endswith(('.png', '.jpg', '.jpeg'))]
            query = ' '.join([part for part in query_parts if part not in image_paths])
            message = {
                "query": query,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "imgs": image_paths
            }
            print(message)
            response = agent.send_message(message)
            print(f"PersonaVLM Agent: {response}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"An error occurred: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Start an interactive chat session with the PersonaVLM Agent."
    )
    parser.add_argument(
        '--force-retrieve', 
        action='store_true', 
        help="Force the agent to retrieve information for every message."
    )
    parser.add_argument(
        '--reasoning-mode', 
        action='store_false', 
        help="Enable reasoning mode for the agent."
    )
    args = parser.parse_args()
    chat(args)


if __name__ == "__main__":
    main()
