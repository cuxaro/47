# 47 · Patrimonio declarado de cargos públicos

Rastrea las **declaraciones de bienes** que los cargos públicos están obligados a presentar,
las pasa a tablas y las publica en una web con filtros.

Los datos salen de los boletines oficiales. El programa que los extrae está en este mismo
repositorio, para que cualquiera pueda repetir el proceso y comprobarlo.

## Qué hay ahora

| Ámbito | Estado |
| --- | --- |
| Les Corts Valencianes (99 diputados y diputadas, XI legislatura) | ✅ hecho |
| Consell y altos cargos de la Generalitat | ⏳ pendiente (ver «Lo que falta») |
| Diputaciones y ayuntamientos | ⏳ pendiente |
| Estado (Congreso, Senado, Gobierno) | ⏳ pendiente |

## Cómo se usa

- **Web con filtros:** carpeta [`docs/`](docs/). Se publica con GitHub Pages
  (Settings → Pages → rama `main`, carpeta `/docs`).
- **Datos en CSV:** carpeta [`datos/`](datos/).

| Fichero | Una fila por… |
| --- | --- |
| `personas.csv` | persona, con sus totales (viviendas, provincias, cuentas, deudas, rentas…) |
| `inmuebles.csv` | inmueble declarado |
| `otros_bienes.csv` | bien no inmobiliario (cuenta, vehículo, acciones, plan de pensiones…) |
| `pasivo.csv` | deuda (hipoteca, préstamo…) |
| `rentas.csv` | partida de la declaración anual de rentas |
| `declaraciones.json` | todo, incluido el histórico de declaraciones de cada persona |

## Qué se puede preguntar y qué no

Sí: cuántos tienen vivienda, cuántos tienen más de dos, cuántos comparten vivienda,
en qué provincias, valor catastral, dinero en cuentas, vehículos, deudas, hipotecas, rentas.

No, porque **la declaración no lo trae**:

- municipio, dirección o si está en la costa: solo figura la **provincia**;
- metros cuadrados;
- valor de mercado: solo el **valor catastral**, que suele ser bastante menor.

Además:

- Son datos **declarados por cada persona**. Nadie los verifica públicamente.
- La descripción de cuentas, vehículos y deudas es voluntaria: hay quien detalla y quien solo da el total.

## De dónde salen los datos

1. **Quién**: lista de diputados en la web de Les Corts.
2. **Dónde**: el Butlletí Oficial de les Corts Valencianes (BOCV) publica la declaración inicial,
   las modificaciones de cada año y la declaración final. El programa busca esos boletines solo.
3. **Rentas**: un PDF de «declaración anual de rentas» por persona, en su ficha.

## Cómo se leen

Dentro del boletín hay tres tipos de formulario, y el programa distingue cada uno:

| Tipo | Cómo se lee | Fiabilidad |
| --- | --- | --- |
| Rellenado en digital | se lee el texto del PDF | alta |
| Impreso y escaneado | se detectan las casillas y se pasa OCR a cada una | buena, con erratas posibles |
| Escrito a mano | el OCR no sirve | hay que transcribirlo a mano |

Controles de calidad:

- Cada casilla escaneada se lee **dos veces**. Si las lecturas no coinciden, el dato se marca como dudoso.
- Se comprueba que **la suma de las líneas dé el total** que declara la persona. Si con otra lectura
  cuadra, se usa esa.
- Todo dato enlaza con **la página exacta del boletín** de donde sale.
- En `personas.csv`, la columna `revisar` indica qué declaraciones conviene mirar a mano, y por qué.

## Ejecutarlo

En GitHub: pestaña **Actions → Extraer declaraciones → Run workflow**. También se ejecuta solo cada lunes.

En tu ordenador (Linux o macOS):

```bash
sudo apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-cat poppler-utils
pip install -r requirements.txt
python -m extractor          # descarga, lee y genera datos/ y docs/datos.json
python -m extractor --sin-red  # sin descargar nada, con lo que haya en .cache/
```

La primera vez tarda (hay unas 500 páginas escaneadas). Después usa la caché.

**No hace falta ninguna clave.** Todas las fuentes son públicas. Si alguna vez hiciera falta una,
va en `.env` (que no se sube) o en los *Secrets* de GitHub, nunca en el código: ver [`.env.example`](.env.example).

## Estructura

```
extractor/
  corts.py      de dónde se descarga (lista de diputados, boletines, rentas)
  red.py        descargas educadas, con pausa y caché
  paginas.py    PDF → palabras y casillas (texto u OCR)
  md3.py        formulario de actividades y bienes
  md4.py        formulario de rentas
  construir.py  une todo y escribe las tablas
docs/           la web
datos/          los CSV
tests/          pruebas
```

## Lo que falta

- **Altos cargos de la Generalitat.** Se publican en el portal GVA Oberta, que no permite el acceso
  automático (`robots.txt`). Opciones: pedir los datos por derecho de acceso, o usar su publicación en el DOGV.
- **Actividades** (cargos, empresas) de cada declaración: el formulario las trae, aún no se tabulan.
- Diputaciones, ayuntamientos y ámbito estatal.

## Aviso legal

Los datos proceden de publicaciones oficiales que la ley obliga a hacer públicas
(Reglamento de Les Corts, art. 21; Ley 8/2016 de la Generalitat). Su reutilización está amparada por la
Ley 37/2007. Se reproduce lo publicado, citando la fuente, sin añadir datos personales de otro origen.
Si encuentras un error, abre una incidencia.
