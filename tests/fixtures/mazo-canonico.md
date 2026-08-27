# Fundamentos de AWS

## ¿Que modelo de facturacion de DynamoDB conviene con trafico impredecible?

- [ ] Provisioned con capacidad fija
- [x] On-Demand (PAY_PER_REQUEST)
- [ ] Reserved Capacity a un ano

> On-Demand cobra por peticion y escala sin configuracion previa, asi que no
> hay que estimar capacidad ni arriesgar throttling en los picos.
>
> Provisioned sale mas barato solo cuando el trafico es sostenido y predecible.

## En una Lambda disparada por S3, ¿de donde se obtiene el nombre del bucket?

- [x] Del propio evento, en `record["s3"]["bucket"]["name"]`
- [ ] De una variable de entorno inyectada por CloudFormation
- [ ] Hay que llamar a `s3:ListBuckets` para descubrirlo

> El evento ya trae bucket y clave. Inyectar el nombre como variable de entorno
> ademas crearia una dependencia circular en la plantilla SAM.

## ¿Que clave permite leer un mazo completo con un solo Query?

- [ ] Un Scan filtrando por `deckId`
- [x] `deckId` como Partition Key
- [ ] Un indice secundario global sobre `prompt`

> Todos los items que comparten Partition Key viven en la misma particion
> logica, asi que un unico Query los recupera.
