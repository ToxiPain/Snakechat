# Utilidad: descarga y regenera binary/tokens.py desde el repositorio oficial de Baileys
import ast
import re
import urllib.request

BAILEYS_CONSTANTS_URL = (
    "https://raw.githubusercontent.com/WhiskeySockets/Baileys/master/src/WABinary/constants.ts"
)

def strip_ts_comments(code: str) -> str:
    pattern = r"('(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")|//[^\n]*"
    return re.sub(pattern, lambda m: m.group(1) or "", code)

def extract_array(source: str, var_name: str):
    match = re.search(rf"export const {var_name}\s*=\s*(\[[\s\S]*?\n\])", source)
    if not match:
        raise RuntimeError(f"No se encontró {var_name} en constants.ts")
    raw = strip_ts_comments(match.group(1))
    return ast.literal_eval(raw)

def main():
    print("[*] Descargando diccionario WABinary v3 oficial desde Baileys...")
    req = urllib.request.Request(
        BAILEYS_CONSTANTS_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        ts_code = resp.read().decode("utf-8")

    single_tokens = extract_array(ts_code, "SINGLE_BYTE_TOKENS")
    double_tokens = extract_array(ts_code, "DOUBLE_BYTE_TOKENS")

    output_path = "../binary/tokens.py"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Archivo generado automáticamente desde Baileys constants.ts\n\n")
        f.write(f"SINGLE_BYTE_TOKENS = {single_tokens!r}\n\n")
        f.write(f"DOUBLE_BYTE_TOKENS = {double_tokens!r}\n")

    print(
        f"[+] binary/tokens.py generado con éxito "
        f"({len(single_tokens)} tokens simples, {len(double_tokens)} tablas dobles)."
    )

if __name__ == "__main__":
    main()
