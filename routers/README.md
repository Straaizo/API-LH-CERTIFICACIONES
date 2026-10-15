# Routers

Cada archivo es un **router** de FastAPI que agrupa endpoints de un módulo (igual que en API-BASE-LH).

## Cómo crear un nuevo router

### 1. Crear el archivo

```python
# routers/mi_modulo.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from utils.auth import usuario_actual
from utils.comunes import filtrar_unidades
from utils.db import get_db
from utils.modelos import Usuario, MiTabla

router = APIRouter(prefix="/mi-modulo")


@router.get("", summary="Listar elementos")
def listar(unidad_id: int | None = None, usuario: Usuario = Depends(usuario_actual),
           db: Session = Depends(get_db)) -> list[dict]:
    consulta = filtrar_unidades(select(MiTabla), MiTabla.unidad_id, usuario, unidad_id=unidad_id)
    return [{"id": x.id, "nombre": x.nombre} for x in db.scalars(consulta)]
```

### 2. Registrarlo en `main.py`

Agregar una tupla a la lista `ROUTERS` (queda bajo `/api` con su tag):

```python
(mi_modulo, "🧩 Mi módulo"),
```

Y, si corresponde, una tarjeta en `MODULES` de `utils/docs_html.py`.

## Utilidades disponibles

| Import | Uso |
|---|---|
| `from utils.db import get_db` | Sesión de base de datos (`Depends(get_db)`) |
| `from utils.auth import usuario_actual` | Usuario autenticado (demo o Firebase) |
| `from utils.auth import solo_certificaciones, puede_escribir` | Dependencias por rol |
| `from utils.auth import verificar_unidad` | 403 si el usuario no tiene acceso a la unidad |
| `from utils.comunes import filtrar_unidades` | Aplica permisos por unidad y filtros de empresa/unidad a una consulta |
| `from utils.bitacora import registrar` | Registrar todo cambio de datos de negocio |
| `from utils import almacenamiento` | URLs firmadas para subir y bajar archivos |

## Reglas

- Validar permisos en la API, no solo en el frontend.
- Todo cambio de datos de negocio pasa por `registrar(...)` antes del `commit`.
- Al agregar o cambiar un endpoint, documentar en `README.md` qué espera el frontend.
