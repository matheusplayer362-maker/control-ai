"""Skill default para expansao de ideias."""


def handle(text: str) -> str:
    return (
        "Plano de expansao da ideia:\n"
        f"1. Objetivo principal: {text}\n"
        "2. Divida em modulos menores com entregas semanais.\n"
        "3. Defina metrica de sucesso e riscos.\n"
        "4. Prototipe rapido, meca resultados e refine."
    )
