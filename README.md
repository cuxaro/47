# 47 · Patrimonio declarado de cargos públicos

Rastrea las **declaraciones de bienes** que los cargos públicos están obligados a presentar,
las pasa a tablas y las publica en una web con filtros.

Empieza por la **Comunitat Valenciana**. Los datos salen de boletines oficiales y portales de transparencia. El programa que los extrae está en este mismo
repositorio, para que cualquiera pueda repetir el proceso y comprobarlo.

## Qué hay ahora

| Ámbito | Estado |
| --- | --- |
| Les Corts Valencianes (99 diputados y diputadas, XI legislatura) | ✅ declaración completa |
| Diputació de València | ✅ solo totales |
| Diputación de Alicante | ✅ solo totales |
| Ayuntamientos de la provincia de València que publican en el BOP | ✅ solo totales |
| Ayuntamientos con las declaraciones en su web (lista en [`fuentes/`](fuentes/)) | 🟡 empezado |
| Diputación de Castellón, resto de ayuntamientos | ⏳ sin fuente automática (ver «Lo que falta») |
| Consell y altos cargos de la Generalitat | ⏳ pendiente (ver «Lo que falta») |
| Estado (Congreso, Senado, Gobierno) | ⏳ pendiente |

### Ojo: dos niveles de detalle

- **Les Corts** publican la declaración entera: cada inmueble, cada cuenta, cada deuda.
- **Diputaciones y ayuntamientos** solo publican **tres cifras por persona**: valor de los inmuebles,
  valor de los demás bienes y deudas. Lo fija la norma (Decreto 191/2010 del Consell y art. 131 de la
  Ley 8/2010). **No se puede saber cuántas viviendas tienen ni dónde.**

En la web, los filtros de viviendas y provincias solo cuentan a quienes tienen declaración completa.
Los de importes (catastral, otros bienes, deudas) valen para todos.

## Cómo se usa

- **Web con filtros:** carpeta [`docs/`](docs/). Se publica con GitHub Pages
  (Settings → Pages → rama `main`, carpeta `/docs`).
- **Datos en CSV:** carpeta [`datos/`](datos/).

| Fichero | Una fila por… |
| --- | --- |
| `personas.csv` | persona, con sus totales (viviendas, provincias, cuentas, deudas, rentas…). La columna `detalle` dice si la declaración es `completo` o solo `totales` |
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

### Les Corts

1. **Quién**: lista de diputados en la web de Les Corts.
2. **Dónde**: el Butlletí Oficial de les Corts Valencianes (BOCV) publica la declaración inicial,
   las modificaciones de cada año y la declaración final. El programa busca esos boletines solo.
3. **Rentas**: un PDF de «declaración anual de rentas» por persona, en su ficha.

### Diputaciones y ayuntamientos

| Fuente | Cómo se obtiene |
| --- | --- |
| Diputació de València | datos abiertos de su portal de altos cargos (un PDF por declaración) |
| Diputación de Alicante | anuncios del BOP colgados en su portal de transparencia |
| Ayuntamientos de València | buscador del BOP de València: anuncios «declaraciones de bienes» desde junio de 2023 |
| Ayuntamientos con web propia | la página que se indique en `fuentes/ayuntamientos_web.json` |

Aquí no hay una lista previa de personas: salen de los propios anuncios. Por eso:

- **Solo aparece quien ha publicado.** La mayoría de ayuntamientos no publica sus declaraciones en el
  BOP aunque la norma lo pide; esos no salen.
- **«En activo» es aproximado**: quien tiene una declaración de este mandato y ningún cese posterior.
  Un cese sin anuncio no se detecta.
- Además de concejales, algunos ayuntamientos (València, Gandia) publican las de su **personal directivo**.
  La columna `clase_cargo` los distingue.

Para añadir un ayuntamiento que tenga los PDF en su web, pon su página en
[`fuentes/ayuntamientos_web.json`](fuentes/ayuntamientos_web.json) y ejecuta. Antes de leer nada, el programa
comprueba el `robots.txt` de cada web y, si no lo permite, no entra.

## Cómo se leen

Dentro del boletín hay tres tipos de formulario, y el programa distingue cada uno:

| Tipo | Cómo se lee | Fiabilidad |
| --- | --- | --- |
| Rellenado en digital | se lee el texto del PDF | alta |
| Impreso y escaneado | se detectan las casillas y se pasa OCR a cada una | buena, con erratas posibles |
| Escrito a mano | el OCR no sirve | se transcribe a mano en [`correcciones/`](correcciones/) |

Controles de calidad:

- Cada casilla escaneada se lee **dos veces**. Si las lecturas no coinciden, el dato se marca como dudoso.
- Se comprueba que **la suma de las líneas dé el total** que declara la persona. Si con otra lectura
  cuadra, se usa esa.
- Todo dato enlaza con **la página exacta del boletín** de donde sale.
- En `personas.csv`, la columna `revisar` indica qué declaraciones conviene mirar a mano, y por qué.
  Solo salta por problemas de *lectura*. Las rarezas de lo que la persona escribió
  (sumas que no dan, cuentas anotadas como deudas…) se anotan, pero no cuentan como error.

Qué declaración se muestra de cada persona: la **última** publicada. Si la última es una modificación
que no repite los inmuebles (hay quien solo anota lo que cambia), se muestra la anterior completa y se avisa.

### Correcciones a mano

`correcciones/corts.json` guarda las declaraciones transcritas a la vista del original, con el número
del sello de registro como clave. Cada una se ha comprobado con las sumas que declara la propia persona.
Para corregir un dato mal leído, añade ahí la declaración y vuelve a ejecutar.

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
  corts.py      Les Corts: lista de diputados, boletines, rentas
  locales.py    diputaciones y ayuntamientos
  bopv.py       buscador del BOP de València
  modelo191.py  lector del resumen de totales (fichas y tablas)
  red.py        descargas educadas, con pausa y caché
  paginas.py    PDF → palabras y casillas (texto u OCR)
  md3.py        formulario de actividades y bienes
  md4.py        formulario de rentas
  construir.py  une todo y escribe las tablas
correcciones/   transcripciones a mano de lo que el OCR no puede leer
fuentes/        lista de ayuntamientos con las declaraciones en su web
docs/           la web
datos/          los CSV
tests/          pruebas
```

## Lo que falta

- **Altos cargos de la Generalitat.** Se publican en el portal GVA Oberta, que no permite el acceso
  automático (`robots.txt`). Opciones: pedir los datos por derecho de acceso, o usar su publicación en el DOGV.
- **Actividades** (cargos, empresas) de cada declaración: el formulario las trae, aún no se tabulan.
- **Provincia de Alicante (ayuntamientos).** El BOP de Alicante no permite el acceso automático
  (`robots.txt`). Solo entran los ayuntamientos que cuelgan los PDF en su propia web.
- **Provincia de Castellón.** No se ha encontrado fuente automática: el BOP de Castellón rechaza las
  peticiones del programa y el portal de la Diputación no publica las declaraciones.
- **Ayuntamientos que no publican.** Se podría pedir por derecho de acceso.
- Ámbito estatal.

## Aviso legal

Los datos proceden de publicaciones oficiales que la ley obliga a hacer públicas
(Reglamento de Les Corts, art. 21; Ley 8/2016 de la Generalitat; Ley 7/1985, art. 75.7;
Ley 8/2010 de la Generalitat, art. 131; Decreto 191/2010 del Consell). Su reutilización está amparada por la
Ley 37/2007. Se reproduce lo publicado, citando la fuente, sin añadir datos personales de otro origen.
Si encuentras un error, abre una incidencia.
