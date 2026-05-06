# TITAN MASTER BRAIN - INNER DIALOGUE ENGINE
# STEP 3: Dialogue using context understanding.

def generate_inner_dialogue(master_input, context):
    d = []

    d.append("I am not only reading data now. I am building market context.")
    d.append(f"Market type: {context.get('market_type')}")
    d.append(f"Trading mode: {context.get('trading_mode')}")
    d.append(f"Risk level: {context.get('risk_level')}")
    d.append(f"Setup environment: {context.get('setup_environment')}")
    d.append(f"Learning environment: {context.get('learning_environment')}")
    d.append(f"Context confidence: {context.get('context_confidence')}")

    d.append("Reasoning summary:")
    for item in context.get("why", []):
        d.append(f"- {item}")

    d.append("Recommended stance:")
    for item in context.get("recommended_stance", []):
        d.append(f"- {item}")

    if context.get("next_questions"):
        d.append("Questions I must investigate next:")
        for q in context.get("next_questions", []):
            d.append(f"- {q}")

    d.append("Final rule: I must understand the situation before ranking or trusting any setup.")

    return d


def print_inner_dialogue(dialogue):
    for line in dialogue:
        print("[InnerDialogue]", line)