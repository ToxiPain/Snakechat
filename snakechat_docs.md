# 📖 SnakeChat — Mapa completo de archivos, funciones y variables

> Pequeña Guia de algunas cosas del proyecto en desarrollo.

---

## 📂 `client.py` — Cliente principal

Orquesta la conexión WebSocket, el handshake Noise XX y el bucle de eventos.

### Variables de módulo
| Nombre | Para qué sirve |
|---|---|
| `WA_WS_URL` | URL del WebSocket de WhatsApp Web |
| `WA_ORIGIN` | Header `Origin` que se envía al conectar |
| `WA_HEADER` | Bytes mágicos `WA\x06\x03` que inician la sesión |
| `WA_USER_AGENT` | User-Agent de Chrome que el cliente finge ser |
| `FALLBACK_WA_VERSION` | Versión de WA usada si falla la descarga dinámica |

### Clase `SnakeChatClient`
Punto de entrada principal; contiene toda la lógica de conexión y eventos.

| Atributo | Para qué sirve |
|---|---|
| `self.debug` | Activa prints detallados de nodos enviados/recibidos |
| `self.wa_version` | Tupla `(major, minor, patch)` de la versión WA detectada |
| `self.pairing` | Instancia `PairingState` con credenciales y lógica QR |
| `self.prekeys` | Instancia `PreKeyStore` con pre-keys Signal de un solo uso |
| `self.signal` | Instancia `SignalSessionManager` para cifrado E2E |
| `self._ws` | Objeto WebSocket activo (o `None` si desconectado) |
| `self._transport` | Canal `NoiseTransport` cifrado activo |
| `self._handlers` | Dict `{evento: [callbacks]}` para el sistema de eventos |
| `self._prekey_seq` | Contador secuencial para IDs de uploads de pre-keys |

### Métodos
| Nombre | Para qué sirve |
|---|---|
| `on(event)` | Decorador para registrar listeners de eventos (`"message"`, `"ready"`, `"node"`) |
| `_emit(event, *args)` | Llama todos los callbacks registrados para un evento |
| `_fetch_latest_wa_version()` | Descarga `sw.js` de WA y extrae `client_revision` |
| `_build_frame(payload, include_header)` | Prefija 3 bytes de longitud (y opcionalmente `WA_HEADER`) |
| `_unpack_transport(raw_decrypted)` | Elimina el byte de flags y descomprime zlib si es necesario |
| `send_node(node)` | Envía un `BinaryNode` usando el transporte activo |
| `send_text(to_jid, text)` | Envía un mensaje de texto cifrado a un JID |
| `_connect_once()` | Abre el WebSocket, hace handshake y corre el bucle de lectura; devuelve `True` si hay que reconectar |
| `start()` | Loop externo que llama a `_connect_once()` y reconecta si es necesario |

---

## 📂 `wapipeline/` — Capa de mensajería (antes `messaging/`)

### `wapipeline/__init__.py`
Re-exporta todo lo público del paquete.

| Exportado | Viene de |
|---|---|
| `send_node` | `transport.py` |
| `send_text` | `send_msg.py` |
| `extract_text` | `receive.py` |
| `build_ack` | `receive.py` |
| `build_retry_receipt` | `receive.py` |
| `handle_node` | `handler.py` |
| `IncomingMessage` | `connection.py` |
| `keepalive_loop` | `connection.py` |

---

### `wapipeline/transport.py` — Capa de transporte

| Nombre | Para qué sirve |
|---|---|
| `send_node(ws, transport, node, debug)` | Serializa un `BinaryNode`, lo cifra con Noise y lo envía por WebSocket con prefijo de 3 bytes de longitud |

---

### `wapipeline/send_msg.py` — Envío de mensajes

| Nombre | Para qué sirve |
|---|---|
| `send_text(ws, transport, signal_session, to_jid, text, debug)` | Construye un `WAMessage`, lo cifra con Signal y lo envía como nodo `<message>` estructurado |
| `keepalive_loop(ws, transport, debug)` | *(duplicado en connection.py)* Loop async que manda pings `iq` cada 25 segundos |

---

### `wapipeline/receive.py` — Procesamiento de mensajes entrantes

| Nombre | Para qué sirve |
|---|---|
| `extract_text(raw_proto)` | Parsea bytes protobuf de `WAMessage` y extrae el texto plano (conversation o extended_text) |
| `print_incoming_message(node, sender, text)` | Imprime en consola el mensaje recibido formateado con nombre y ID |
| `build_ack(node)` | Construye el nodo `<ack>` de confirmación de recepción para cualquier nodo entrante |
| `build_retry_receipt(node, pairing, prekeys)` | Construye un recibo `<receipt type="retry">` con claves frescas cuando el descifrado falla |

---

### `wapipeline/handler.py` — Dispatcher de nodos entrantes

| Nombre | Para qué sirve |
|---|---|
| `_print_incoming(node, sender, text)` | Función interna de log de mensaje recibido |
| `handle_node(node, client)` | Función principal: recibe cualquier `BinaryNode` y lo despacha según su `tag` (`success`, `ack`, `stream:error`, `notification`, `receipt`, `call`, `message`). Devuelve `True` si hay que reconectar |
| `_handle_prekey_refill(node, client)` | Si la notificación `encrypt` indica pocas pre-keys (`< 10`), sube 30 nuevas |
| `_handle_message(node, client)` | Descifra el mensaje (`pkmsg` o `msg`), emite `"message"` al cliente, o pide retry si falla |

---

### `wapipeline/connection.py` — Estado de conexión

#### Clase `IncomingMessage`
Dataclass que representa un mensaje recibido ya procesado.

| Campo | Para qué sirve |
|---|---|
| `id` | ID único del mensaje (string hexadecimal) |
| `sender` | JID completo del remitente |
| `sender_pn` | Número de teléfono del remitente (opcional) |
| `push_name` | Nombre de contacto / notificación del remitente |
| `text` | Texto plano extraído |
| `raw_node` | `BinaryNode` original sin procesar |

| Función | Para qué sirve |
|---|---|
| `keepalive_loop(ws, transport, debug)` | Loop async que envía pings `iq` cada 25 s para mantener viva la conexión |

---

## 📂 `binary/` — Protocolo binario WABinary

### `binary/__init__.py`
Re-exporta `BinaryNode`, `decode_binary_node`, `encode_binary_node`.

### `binary/wabinary.py` — Serialización WABinary

#### Diccionarios de tokens
| Nombre | Para qué sirve |
|---|---|
| `TAGS` | Dict de constantes de tipo de dato binario (`LIST_EMPTY`, `AD_JID`, `JID_PAIR`, etc.) |
| `SINGLE_TOKEN_MAP` | Mapea string → índice de token de 1 byte |
| `DOUBLE_TOKEN_MAP` | Mapea string → `(dict_idx, tok_idx)` para tokens de 2 bytes |

#### Clase `BinaryNode`
Nodo del árbol binario de protocolo WA.

| Campo | Para qué sirve |
|---|---|
| `tag` | Nombre del nodo (`"message"`, `"iq"`, `"ack"`, etc.) |
| `attrs` | Diccionario de atributos `{nombre: valor}` |
| `content` | Contenido: `None`, `bytes`, lista de `BinaryNode` hijos, o string |

| Método | Para qué sirve |
|---|---|
| `get_child(tag)` | Devuelve el primer hijo con ese tag, o `None` |
| `get_children(tag)` | Devuelve todos los hijos con ese tag |
| `__repr__()` | Representación legible tipo XML para debug |

#### Clase interna `_Decoder`
| Método | Para qué sirve |
|---|---|
| `read_byte()` | Lee 1 byte avanzando el cursor |
| `read_bytes(n)` | Lee `n` bytes avanzando el cursor |

#### Funciones de módulo
| Nombre | Para qué sirve |
|---|---|
| `decode_binary_node(data)` | Deserializa bytes WABinary → árbol de `BinaryNode` |
| `encode_binary_node(node)` | Serializa un `BinaryNode` → bytes WABinary |

### `binary/tokens.py`
| Nombre | Para qué sirve |
|---|---|
| `SINGLE_BYTE_TOKENS` | Lista de ~256 strings: tokens que caben en 1 byte |
| `DOUBLE_BYTE_TOKENS` | Lista de 4 listas de ~256 strings: tokens de 2 bytes (diccionarios 0–3) |

---

## 📂 `crypto/` — Criptografía

### `crypto/__init__.py`
Re-exporta: `NoiseTransport`, `NoiseHandshakeState`, `generate_x25519_keypair`, `xeddsa_sign`, `SignalSessionManager`.

### `crypto/noise.py` — Transporte Noise activo

#### Clase `NoiseTransport`
Canal cifrado post-handshake (AES-GCM con contadores separados de escritura/lectura).

| Atributo | Para qué sirve |
|---|---|
| `write_cipher` | `AESGCM` para cifrar saliente |
| `read_cipher` | `AESGCM` para descifrar entrante |
| `write_counter` | Contador de nonce de escritura (evita reutilizar IV) |
| `read_counter` | Contador de nonce de lectura |

| Método | Para qué sirve |
|---|---|
| `_make_iv(counter)` | Genera IV de 12 bytes: 8 ceros + counter big-endian |
| `encrypt(plaintext)` | Cifra y avanza `write_counter` |
| `decrypt(ciphertext)` | Descifra y avanza `read_counter` |

### `crypto/handshake.py` — Handshake Noise XX

#### Constantes
| Nombre | Para qué sirve |
|---|---|
| `NOISE_PATTERN` | Bytes del patrón `Noise_XX_25519_AESGCM_SHA256` (semilla inicial de `h` y `ck`) |

#### Clase `NoiseHandshakeState`
Implementa el patrón Noise XX: negocia claves efímeras y estáticas.

| Atributo | Para qué sirve |
|---|---|
| `h` | Hash encadenado (mezcla todo lo autenticado) |
| `ck` | Chaining key (alimenta la KDF en cada `mix_key`) |
| `key` | Clave de cifrado simétrica activa |
| `counter` | Contador de nonce para operaciones del handshake |

| Método | Para qué sirve |
|---|---|
| `mix_hash(data)` | Actualiza `h = SHA256(h + data)` |
| `start(header)` | Mezcla el header WA en `h` |
| `authenticate(data)` | Mezcla datos en `h` sin cifrar (para claves públicas) |
| `_generate_iv()` | Genera IV y avanza `counter` |
| `mix_key(data)` | Aplica HKDF con `ck` como salt, actualiza `ck` y `key`, resetea `counter` |
| `encrypt(plaintext)` | Cifra y mezcla el ciphertext en `h` |
| `decrypt(ciphertext)` | Descifra y mezcla el ciphertext en `h` |
| `finish()` | Deriva claves finales con HKDF y devuelve un `NoiseTransport` listo |

### `crypto/keys.py` — Generación de claves y firma XEdDSA

#### Constantes internas (aritmética de curva Ed25519)
| Nombre | Para qué sirve |
|---|---|
| `_P` | Primo de campo (`2^255 - 19`) |
| `_L` | Orden del grupo de la curva |
| `_D` | Coeficiente `d` de Edwards |
| `_BX`, `_BY` | Coordenadas del punto base de Ed25519 |
| `_BASE` | Punto base en coordenadas extendidas |
| `_IDENTITY` | Punto neutro (identidad aditiva) |

#### Funciones internas
| Nombre | Para qué sirve |
|---|---|
| `_point_add(p1, p2)` | Suma de puntos en curva Edwards (coordenadas extendidas) |
| `_scalar_mult(s, point)` | Multiplicación escalar por doble-y-suma |
| `_encode_point(point)` | Serializa punto a 32 bytes little-endian |

#### Funciones públicas
| Nombre | Para qué sirve |
|---|---|
| `generate_x25519_keypair()` | Genera par de claves X25519; devuelve `(priv_obj, priv_bytes, pub_bytes)` |
| `xeddsa_sign(private_key_bytes, message)` | Firma un mensaje con esquema XEdDSA (Curve25519 → Ed25519 compatible con Signal) |

### `crypto/signal.py` — Motor Signal E2E

#### Clase `SignalSessionManager`
Gestiona sesiones Signal (X3DH + Double Ratchet) por JID.

| Atributo | Para qué sirve |
|---|---|
| `ident_priv_bytes` | Bytes de la clave de identidad privada |
| `ident_pub_bytes` | Bytes de la clave de identidad pública |
| `skey_priv_bytes` | Bytes de la signed pre-key privada |
| `prekeys` | Referencia al `PreKeyStore` para obtener claves efímeras |
| `_sessions` | Dict `{jid: session_state}` de sesiones activas |

| Método | Para qué sirve |
|---|---|
| `decrypt_pkmsg(sender, ciphertext)` | Descifra un mensaje de pre-key (primer mensaje de una sesión nueva, X3DH) |
| `decrypt_msg(sender, ciphertext)` | Descifra un mensaje normal de sesión establecida (Double Ratchet) |
| `encrypt_msg(to_jid, plaintext)` | Cifra un mensaje con la sesión Signal del destinatario |

---

## 📂 `state/` — Estado persistente

### `state/__init__.py`
Re-exporta `PairingState` y `PreKeyStore`.

### `state/pairing.py` — Vinculación QR y credenciales

#### Constantes
| Nombre | Para qué sirve |
|---|---|
| `CREDS_PATH` | Ruta a `creds.json` donde se persiste la sesión |

#### Funciones auxiliares
| Nombre | Para qué sirve |
|---|---|
| `_b64e(data)` | Convierte bytes → string base64 |
| `_b64d(text)` | Convierte string base64 → bytes |

#### Clase `PairingState`
Mantiene todas las claves y credenciales de sesión.

| Atributo | Para qué sirve |
|---|---|
| `wa_version` | Versión de WA para incluir en el payload del cliente |
| `creds_path` | Ruta donde se guarda/carga `creds.json` |
| `jid` | JID completo del usuario (`número@s.whatsapp.net`) |
| `lid` | LID del dispositivo multi-device |
| `account_bytes` | Bytes del ADV identity firmado por el servidor |
| `key_index` | Índice de la clave de dispositivo |
| `static_priv` / `static_priv_bytes` / `static_pub` | Par de claves estática X25519 (para handshake Noise) |
| `ident_priv_bytes` / `ident_pub_bytes` | Par de identidad Signal (X3DH) |
| `skey_priv_bytes` / `skey_pub_bytes` | Signed pre-key Signal |
| `adv_secret_key` | Clave secreta ADV (32 bytes aleatorios) |
| `reg_id` | ID de registro aleatorio Signal |

| Propiedad / Método | Para qué sirve |
|---|---|
| `is_registered` | `True` si ya hay JID guardado (sesión activa) |
| `_init_fresh_keys()` | Genera todas las claves nuevas para primera vez |
| `_load_creds()` | Carga credenciales desde `creds.json` |
| `save_creds()` | Persiste las credenciales actuales en `creds.json` |
| `build_client_payload()` | Construye el `ClientPayload` protobuf que se envía al servidor |
| `handle_node(node)` | Procesa nodos de pairing (`pair-device`, `pair-success`) y devuelve respuesta o `None` |

### `state/prekeys.py` — Almacén de pre-keys Signal

#### Constantes
| Nombre | Para qué sirve |
|---|---|
| `PREKEYS_PATH` | Ruta a `prekeys.json` |

#### Funciones auxiliares
| Nombre | Para qué sirve |
|---|---|
| `_b64e(data)` | bytes → base64 |
| `_b64d(text)` | base64 → bytes |

#### Clase `PreKeyStore`
Pre-keys efímeras de un solo uso para el protocolo X3DH de Signal.

| Atributo | Para qué sirve |
|---|---|
| `store_path` | Ruta del archivo JSON de almacenamiento |
| `next_id` | Próximo ID de pre-key a generar |
| `keys` | Dict `{id_str: {priv: b64, pub: b64}}` de claves disponibles |

| Método | Para qué sirve |
|---|---|
| `_load()` | Carga el store desde disco |
| `_save()` | Persiste el store en disco |
| `generate_batch(count)` | Genera `count` pre-keys nuevas, las guarda y devuelve lista de `(id, pub_bytes)` |
| `get_private_key(key_id)` | Devuelve la clave privada de una pre-key por ID |
| `build_upload_iq(iq_id, reg_id, ...)` | Construye el nodo `<iq xmlns="encrypt">` para subir pre-keys al servidor |

---

## 📂 `protobuf/` — Mensajes protobuf

### `protobuf/__init__.py`
Re-exporta los tipos generados: `HandshakeMessage`, `ClientPayload`, `DeviceProps`, `WAMessage`, `ADVSignedDeviceIdentityHMAC`, `ADVSignedDeviceIdentity`, `ADVDeviceIdentity`, `HOSTED`.

### `protobuf/handshake.proto` / `handshake_pb2.py`
Mensajes del handshake: `HandshakeMessage` (con `ClientHello`, `ServerHello`, `ClientFinish`), `ClientPayload`, `DeviceProps`.

### `protobuf/signal.proto` / `signal_pb2.py`
Mensajes Signal: `WAMessage` (con `conversation`, `extended_text_message`), `SenderKeyDistributionMessage`.

---

## 📂 `example/example.py` — Ejemplo de uso

| Nombre | Para qué sirve |
|---|---|
| `client` | Instancia global de `SnakeChatClient` |
| `on_ready(jid)` | Callback del evento `"ready"`: imprime que el cliente está conectado |
| `on_message(msg)` | Callback del evento `"message"`: imprime el mensaje y responde `"!ping"` → `"¡Pong!"` |

---

## 📂 `tools/sync_tokens.py`
Script de utilidad para sincronizar/actualizar `binary/tokens.py` con la última versión de los tokens WABinary desde la web de WhatsApp.

---

## 🗂 Resumen visual de módulos

```
SnakeChat
├── client.py              ← SnakeChatClient (punto de entrada)
├── wapipeline/            ← Mensajería (antes: messaging/)
│   ├── transport.py       ←   send_node()
│   ├── send_msg.py        ←   send_text()
│   ├── receive.py         ←   extract_text(), build_ack(), build_retry_receipt()
│   ├── handler.py         ←   handle_node()
│   └── connection.py      ←   IncomingMessage, keepalive_loop()
├── binary/                ← Protocolo WABinary
│   ├── wabinary.py        ←   BinaryNode, encode/decode
│   └── tokens.py          ←   tablas de tokens de 1 y 2 bytes
├── crypto/                ← Criptografía
│   ├── noise.py           ←   NoiseTransport
│   ├── handshake.py       ←   NoiseHandshakeState
│   ├── keys.py            ←   generate_x25519_keypair(), xeddsa_sign()
│   └── signal.py          ←   SignalSessionManager
├── state/                 ← Persistencia
│   ├── pairing.py         ←   PairingState (credenciales + QR)
│   └── prekeys.py         ←   PreKeyStore (pre-keys Signal)
├── protobuf/              ← Tipos protobuf generados
└── example/example.py     ← Demo de uso básico
```
