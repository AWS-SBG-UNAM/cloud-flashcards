# Tipografías

La app usa **Amazon Ember**, la tipografía corporativa de AWS.

Los archivos no están versionados: Amazon Ember tiene licencia propietaria y
no se puede redistribuir en un repositorio público.

## Dónde dejarlos

Copia los `.woff2` en esta carpeta con **exactamente** estos nombres:

```
frontend/public/fonts/
├── AmazonEmber-Regular.woff2      (peso 400)
├── AmazonEmber-Medium.woff2       (peso 500)
├── AmazonEmber-Bold.woff2         (peso 700)
└── AmazonEmberMono-Regular.woff2  (peso 400, monoespaciada)
```

Las declaraciones `@font-face` están en `src/index.css`. Si cambias los
nombres, actualízalas allí.

## De dónde salen

Vienen en el mismo media kit del que salió la paleta de colores (AWS Builder
Center / Student Builder Groups). Si solo tienes `.ttf` o `.otf`, conviértelos
a `.woff2` — pesan bastante menos:

```bash
pip install fonttools brotli
fonttools ttLib.woff2 compress AmazonEmber-Regular.ttf
```

## Si no los pones

No pasa nada. `font-display: swap` y la pila de respaldo hacen que el
navegador use la tipografía del sistema (San Francisco en macOS, Segoe UI en
Windows). La app funciona igual, solo cambia el tipo.
