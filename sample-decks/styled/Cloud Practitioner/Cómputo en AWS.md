# Cómputo en AWS

## Una empresa está preocupada por gastar dinero en recursos de cómputo infrautilizados en AWS. ¿Qué función de AWS ayudará a garantizar que sus aplicaciones agreguen/eliminan automáticamente capacidad de cómputo EC2 para que coincida estrechamente con la demanda requerida?

- [ ] AWS Elastic Load Balancer.
- [ ] AWS Budgets.
- [x] AWS Auto Scaling
- [ ] AWS Cost Explorer

> AWS Auto Scaling ajusta automáticamente la capacidad de cómputo (EC2) para que coincida con la demanda. Ayuda a evitar el gasto en recursos infrautilizados.

## ¿Cuál es la diferencia fundamental entre el estado 'Detenido' (Stopped) y 'Terminado' (Terminated) en una instancia de Amazon EC2?

- [x] Las instancias detenidas se pueden volver a iniciar.
- [ ] Solo las instancias terminadas dejan de generar cargos de cómputo.
- [ ] Las instancias terminadas conservan su dirección IP.
- [ ] Detener una instancia elimina automáticamente el volumen raíz, terminarla no.

> Una instancia detenida permite reiniciar la instancia manteniendo su configuración y volúmenes, mientras que la terminación es una eliminación por completo.

## Un desarrollador necesita una 'plantilla' que contenga el sistema operativo y las configuraciones de usuario para lanzar múltiples instancias idénticas. ¿Qué recurso de AWS debe utilizar?

- [ ] Instance Store
- [ ] Key Pair
- [ ] Grupo de Seguridad
- [x] Amazon Machine Image (AMI)

> Una AMI funciona como una unidad empaquetada que incluye el sistema operativo, el servidor de aplicaciones y otras configuraciones necesarias para lanzar una instancia.

## ¿Qué modelo de compra de EC2 ofrece el mayor descuento (hasta un 90%) a cambio de permitir que AWS interrumpa la instancia si necesita recuperar la capacidad?

- [x] Instancias Spot
- [ ] Instancias Dedicadas
- [ ] Instancias Bajo Demanda
- [ ] Instancias Reservadas

> Las instancias Spot aprovechan la capacidad no utilizada de AWS a precios muy bajos en comparación con otros modelos, con la condición de que, si se necesita, AWS puede reclamar esa capacidad con un aviso de 2 minutos.

## ¿Cuáles de los siguientes servicios de AWS pueden utilizarse como recursos de cómputo? (Dos opciones)

- [ ] Amazon VPC
- [ ] Amazon CloudWatch
- [ ] Amazon S3
- [x] Amazon EC2.
- [x] AWS Lambda

> Las demás opciones no son servicios de cómputo.

## ¿Cuál de las siguientes opciones de compra de instancias EC2 admite el modelo Bring Your Own License (BYOL) para casi todos los escenarios posibles?

- [ ] Instancias Dedicadas (Dedicated Instances)
- [x] Hosts Dedicados (Dedicated Hosts)
- [ ] Instancias bajo demanda (On-demand Instances)
- [ ] Instancias Reservadas (Reserved Instances)

> Los **Dedicated Hosts** permiten traer tus propias licencias (BYOL) para Windows Server, SQL Server, etc., con control total del host físico.

## ¿Cuál es el servicio de AWS que te brinda el nivel más alto de control sobre la infraestructura virtual subyacente?

- [ ] Amazon Redshift
- [ ] Amazon DynamoDB
- [x] Amazon EC2
- [ ] Amazon RDS

> Amazon EC2 otorga el nivel más alto de control sobre la infraestructura virtual: sistema operativo, red, almacenamiento y seguridad. Aparte, los demás servicios listados son para bases de datos.

## ¿Cuál de los siguientes servicios te permite ejecutar aplicaciones en contenedores en un clúster de instancias EC2?

- [x] Amazon ECS
- [ ] AWS Data Pipeline
- [ ] AWS Cloud9
- [ ] AWS Personal Health Dashboard

> ECS la única opción relacionada a clústers y contenedores del listado.

## ¿Cuál es el servicio serverless de AWS que te permite ejecutar tus aplicaciones sin ninguna carga administrativa?

- [ ] Amazon Lightsail
- [x] AWS Lambda
- [ ] Instancias de Amazon RDS
- [ ] Instancias de Amazon EC2

> Lightsail ofrece instancias de servidor privado virtual (VPS), RDS es para bases de datos. EC2 no es serverless. Lambda es la única opción serverless de la lista.

## ¿Cuáles de los siguientes recursos de cómputo son serverless? (Dos opciones)

- [ ] EC2
- [x] Fargate
- [x] Lambda
- [ ] ECS
- [ ] EMR

> Son las únicas opciones serverless del listado. EC2 y ECS si quieren crear infra. EMR es un servicio para gestionar clústeres.

## Por razones de cumplimiento y regulaciones, una agencia gubernamental requiere que sus aplicaciones se ejecuten en hardware dedicado exclusivamente para ellos. ¿Cómo se puede cumplir con este requisito?

- [x] Usar EC2 Dedicated Hosts
- [ ] Usar instancias reservadas EC2
- [ ] Usar instancias Spot EC2
- [ ] Usar instancias bajo demanda EC2

> Para cumplimiento y aislamiento físico, los **Dedicated Hosts** aseguran que el hardware subyacente sea **exclusivo** de un cliente.

## ¿Cuál de las siguientes NO es una ventaja de usar AWS Lambda?

- [ ] AWS Lambda ejecuta código sin aprovisionar ni administrar servidores
- [x] AWS Lambda proporciona capacidad de cómputo redimensionable en la nube
- [ ] No hay cargos cuando tu código de AWS Lambda no se está ejecutando.
- [ ] AWS Lambda puede ser invocado directamente desde cualquier aplicación.

> Si pudiera ser redimensionable, ya no sería *serverless*, el cual es el atributo principal de Lambda.

## ¿Cuál es la responsabilidad principal del usuario cuando utiliza Amazon EKS (Elastic Kubernetes Service)?

- [ ] Mantener el Control Plane
- [x] Gestionar los *worker nodes.*
- [ ] Configurar la infraestructura necesaria para ocupar K8s.
- [ ] El usuario tiene toda la responsabilidad del funcionamiento de los kubernetes.

> AWS gestiona el control plane, por lo que el usuario solamente es responsable del mantenimiento y aprovisionamiento de los worker nodes.

## Una startup quiere lanzar un servidor de WordPress de forma rápida, con un precio mensual predecible y sin configuraciones complejas de red. ¿Qué servicio es el más recomendado?

- [x] Lightsail
- [ ] Outposts
- [ ] EKS
- [ ] Lambda

> Lightsail es la opción “amigable” de EC2 que permite lanzar instancias preconfiguradas con cómputo, almacenamiento y redes en un solo paquete económico para proyectos pequeños.

## En la nomenclatura de instancias de EC2 como 't2.micro', ¿qué representa el término 'micro'?

- [ ] La familia de la instancia.
- [ ] El nombre del sistema operativo.
- [x] El tamaño de la instancia y sus recursos.
- [ ] El tamaño del disco de la instancia.

> El tamaño, *micro, small, large, xl*, determina la cantidad de vCPUs, RAM, rendimiento de red, etc.

## ¿Qué herramienta de balanceo de carga de AWS se encarga de decirle al balanceador cómo redirigir las conexiones externas hacia los grupos objetivos (target groups)?

- [ ] Health Checks
- [ ] Rules
- [x] Listeners
- [ ] Nodos

> Los listeners revisan las peticiones de conexión basándose en el protocolo y puerto configurados para decidir que hacer con el tráfico.