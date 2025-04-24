import os

IGNORE = {'__pycache__', '.env', '.git', '.idea', 'audio', "*.md", "logs"}

def list_structure(base_path, prefix=""):
    tree = ""
    items = sorted(os.listdir(base_path))
    for item in items:
        if item in IGNORE:
            continue
        path = os.path.join(base_path, item)
        if os.path.isdir(path):
            tree += f"{prefix}{item}/\n"
            tree += list_structure(path, prefix + "    ")
        else:
            tree += f"{prefix}{item}\n"
    return tree

def list_code_files(base_path):
    code = ""
    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if d not in IGNORE]
        for file in files:
            if file in IGNORE:
                continue
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, base_path)
            code += f"\n{rel_path}:\n"
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    code += f.read() + "\n"
            except Exception as e:
                code += f"Erro ao ler arquivo: {e}\n"
    return code

def main():
    base_path = "."
    structure = list_structure(base_path)
    code_files = list_code_files(base_path)

    with open("code.txt", "w", encoding="utf-8") as f:
        f.write("Estrutura do projeto:\n")
        f.write(structure)
        f.write("\nCódigo fonte:\n")
        f.write(code_files)

    print("Arquivo 'code.txt' criado com sucesso.")

if __name__ == "__main__":
    main()
