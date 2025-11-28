import subprocess
import sys


def run_git_command(command):
    """Executa um comando Git e verifica se houve erros."""
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True, encoding='utf-8')
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar o comando: {' '.join(command)}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("Erro: O comando 'git' não foi encontrado. Verifique se o Git está instalado e no PATH.")
        sys.exit(1)


def main():
    """Função principal para automatizar o deploy no GitHub."""
    try:
        commit_title = input("Digite o título do commit: ")
        if not commit_title:
            print("O título do commit não pode ser vazio. Abortando.")
            sys.exit(1)

        print("Digite a descrição longa (pressione Enter duas vezes para finalizar): ")
        lines = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        commit_description = "\n".join(lines)

    except KeyboardInterrupt:
        print("\nOperação cancelada pelo usuário. Abortando.")
        sys.exit(0)

    print("\n--- Adicionando todos os arquivos (git add .) ---")
    run_git_command(["git", "add", "."])

    print(f"\n--- Criando commit ---")
    # Constrói a mensagem de commit completa
    full_commit_message = commit_title
    if commit_description:
        full_commit_message += "\n\n" + commit_description

    # Passa a mensagem completa como um único argumento para -m
    commit_command = ["git", "commit", "-m", full_commit_message]
    run_git_command(commit_command)

    print("\n--- Enviando para o GitHub (git push) ---")
    run_git_command(["git", "push", "origin", "HEAD"])

    print("\n✅ Projeto enviado com sucesso para o GitHub!")


if __name__ == "__main__":
    main()
