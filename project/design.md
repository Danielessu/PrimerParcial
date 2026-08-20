# Diseño del agente

Este documento debe completarse **antes** de la implementación principal del agente.

Use sus propias palabras y notación. No reemplace este archivo por una transcripción
del enunciado. Las subsecciones existen para que no se le olvide una decisión;
usted decide el contenido.

El entorno, según las propiedades vistas en clase, es totalmente observable,
determinista, secuencial, estático, discreto y de agente único. Bajo esas
condiciones la solución es un **plan completo** y el marco correcto es la
búsqueda clásica. Justifique cada componente con ese marco (AIMA, cap. 3).

---

## Estado

### Definición formal

Escriba la tupla de estado. Cada componente debe ser una variable que el robot
necesita para saber qué podrá hacer después.

```text
s = ⟨ zona_actual, bateria_restante, carga_robot, objetos_en_suelo, estado_puertas, estado_paneles, estado_estaciones ⟩
```

El estado corresponde al panorama completo actualmente del robot y la instalación, por lo que cualquier cambio genera un estado distinto y afecta las acciones futuras del agente. Teniendo esto en cuenta se definieron las siguientes variables para el robot:

- zona_actual: Zona en la que se encuentra el robot. Determina qué corredores puede utilizar, qué objetos puede recoger y con qué elementos puede interactuar.

- bateria_restante: Corresponde a la cantidad de energía restante del robot. Una acción solo puede ejecutarse si la batería disponible cubre su costo incluyendo movimientos, recoger o dejar objetos, abrir puertas, reparar paneles, activar estaciones y recargar.

- carga_robot: Son los elementos que transporta el robot actualmente tales como: llaves, herramientas y materiales. Aquí se determina el peso o capacidad actual, el espacio que tiene disponible y que operaciones puede realizar.

- objetos_en_suelo: Sirve para determinar la ubicación actual de los objetos que no están en la carga del robot, incluyendo llaves, herramientas y materiales. Se requiere porque el robot puede ir recogiendo y dejando objetos en el camino para no exceder la capacidad de carga.

- estado_puertas: Hace referencia al estado actual de las puertas encontradas. Una puerta puede encontrarse abierta o cerrada. Una vez abierta, permite atravesar los corredores y esta no puede volverse a cerrar.

- estado_paneles: Identifica el estado actual de cada panel pudiendo estar dañado o arreglado. Reparar un panel puede cambiar el entorno y puede ser requisito para activar una estación posteriormente.

- estado_estaciones: Identifica el estado actual de cada estación de la instalación. Una estación puede estar offline u online.

### Por qué cada variable es necesaria

Criterio de clase (`Applicable`): una variable pertenece al estado **si y solo si**
dos configuraciones que difieran en ella pueden diferir en las acciones legales
futuras o en su resultado.

Pase ese filtro con cada variable. En particular:

- la **batería** forma parte de la situación física (§2.1 del enunciado);
- la **posición de los objetos** no se deduce del escenario inicial si el robot
  puede soltarlos (`DROP`);
- los cambios permanentes (puertas, paneles, estaciones) condicionan el futuro.


- zona_actual: Esta variable es necesaria porque determina los corredores que el robot puede atravesar, los objetos que puede recoger o dejar y los elementos con los que puede interactuar. Dos estados con distinta zona pueden tener acciones `MOVE`, `PICKUP`, `DROP` o `INTERACT` diferentes.

- bateria_restante: Es necesaria porque toda acción tiene un costo y solo puede ejecutarse si existe suficiente batería. Dos estados pueden ser iguales en todas las demás variables, pero tener distinta batería o diferentes acciones, por lo que una acción puede ser posible en uno e imposible en el otro.

- carga_robot: Esta variable es necesaria porque indica los objetos que transporta el robot. La carga determina algunas de las acciones que puede realizar el robot con los objetos disponibles, como poder abrir una puerta con una llave, reparar un panel con una herramienta y un material, o recoger otro objeto sin superar la capacidad máxima. Además, los materiales de la carga pueden consumirse y las herramientas pueden reutilizarse.

- objetos_en_suelo: Esta variable es necesaria porque los objetos pueden cambiar de ubicación mediante `PICKUP` y `DROP`. La posición actual de una llave, herramienta o material determina si puede recogerse en una zona determinada. Por tanto, no basta con conocer únicamente el escenario inicial.

- estado_puertas: Esta variable es necesaria porque una puerta cerrada bloquea los corredores que controla y una puerta abierta permite atravesarlos. Como las puertas abiertas no vuelven a cerrarse, este cambio modifica las acciones de movimiento disponibles en el futuro.

- estado_paneles: Esta variable es necesaria porque un panel dañado puede repararse y un panel reparado puede ser una dependencia para activar una estación. Por eso, dos estados diferentes en el estado de un panel pueden permitir activaciones diferentes.

- estado_estaciones: Esta variable es necesaria porque una estación puede estar `OFFLINE` u `ONLINE`, y algunas estaciones solo pueden activarse cuando otras se encuentran activas. Como una estación activada permanece `ONLINE`, su estado cambia las acciones futuras y puede modificar el cumplimiento de la meta.

### Qué información se deriva y NO se almacena

Peso de la carga, grafo de corredores, costos, capacidad, batería máxima, etc.
Si se puede calcular a partir del estado y de las constantes del escenario, no
es una variable de estado.


A partir de carga_robot y de las propiedades de los objetos se puede calcular:

- El peso total de la carga.
- La capacidad disponible del robot.
- Si una llave, herramienta o material se encuentra en la carga.
- Si el robot posee los recursos necesarios para una acción.

El grafo de corredores, las zonas conectadas, las puertas asociadas a cada corredor y el costo de cada movimiento se obtienen del escenario. No se almacenan dentro del estado porque no cambian durante el trayecto de la misión.

Otros elementos que también son constantes del escenario:

- La capacidad máxima de transporte.
- La batería máxima.
- Los costos de `PICKUP`, `DROP`, `INTERACT` y `RECHARGE`.
- El peso y las propiedades de cada objeto.
- La ubicación de los paneles, estaciones y cargadores.
- Los requisitos de cada puerta, panel y estación.
- Las zonas que poseen cargadores.

La batería máxima no debe confundirse con la batería restante. La primera es una constante del escenario y permite calcular el resultado de `RECHARGE`; la segunda sí pertenece al estado porque cambia después de cada acción y determina qué acciones pueden ejecutarse.

De manera similar, la meta no se almacena en el estado, porque es una condición fija de la misión. Se consulta sobre `estado_estaciones` mediante la prueba de meta.

El costo acumulado, el padre del nodo, la acción anterior y la lista de acciones ejecutadas tampoco pertenecen al estado físico. Esos datos forman parte del nodo de búsqueda y sirven para reconstruir y comparar caminos, pero no cambian las acciones legales futuras desde una misma situación física.

### Qué pertenece al historial de búsqueda y no al estado físico

`g(n)`, el padre y la acción que trajo aquí describen *cómo llegó*, no *dónde
está*. Viven en el **Nodo**. Si se meten en el estado, CLOSED no puede reconocer
la misma situación física alcanzada por dos rutas.

### Cuándo dos configuraciones son el mismo estado

Materiales equivalentes por tipo (§2.2): no les ponga ids artificiales.
Estructuras canónicas (conjuntos, contadores) para que `==` y el hash coincidan
con la equivalencia física. Sin eso Graph Search explota.

`g(n)` representa el costo acumulado del camino. El padre y la acción anterior sirven para reconstruir el plan cuando se encuentra una solución. Si estos datos se incluyeran en el estado, dos caminos que llegan a la misma situación física se considerarían estados diferentes y CLOSED no podría evitar volverlos a explorar.

Dos configuraciones representan el mismo estado cuando tienen los mismos valores en todas las variables para realizar acciones futuras:

- zona_actual.
- bateria_restante.
- carga_robot.
- objetos_en_suelo.
- estado_puertas.
- estado_paneles.
- estado_estaciones.

La batería sí debe compararse, porque una cantidad diferente de energía puede hacer que una acción sea posible en un estado e imposible en otro.

Los materiales del mismo tipo se consideran equivalentes y se representan mediante cantidades. Por ejemplo, las dos unidades de `FUSE` del escenario no se distinguen como `FUSE_1` y `FUSE_2`; se almacenan como una cantidad igual a dos. Las llaves y herramientas se distinguen por su identificador, porque cada una puede tener una función o requisito diferente.

La representación debe ser canónica: la carga y las colecciones de objetos deben tener un orden único o utilizar estructuras inmutables, y los materiales deben agruparse por tipo, zona y cantidad. Así, dos representaciones diferentes que produzcan la misma situación física generan el mismo estado, el mismo resultado de igualdad y el mismo hash.

La dominancia de batería sirve para optimizar la ruta. Si dos nodos tienen la misma configuración del mundo y uno alcanza esa configuración con un costo menor o igual y con más batería restante, el otro nodo está dominado y puede descartarse porque no puede producir una solución mejor.

### Relevancia: objetos que ya no cambian el futuro

Los cambios del entorno son **monótonos** (una puerta abierta no se cierra).
Pregúntese: una llave cuya puerta ya está abierta, o una herramienta cuyo panel
ya está reparado, ¿sigue distinguiendo estados si solo cambia *dónde* está en
el suelo? Si no habilita ninguna acción futura, incluirla multiplica el espacio
con permutaciones de objetos muertos. Justifique si las ignora y por qué eso
no pierde el óptimo.

Una llave es irrelevante después de que la puerta correspondiente está abierta, porque dicha puerta ya no necesita la llave para atravesarse. Del manera similar, una herramienta deja de ser relevante cuando todos los paneles que requieren dicha herramienta ya están reparados. En esos casos, la posición de esos objetos en el suelo ya no distingue situaciones físicas útiles: cambiarla no modifica los movimientos, recogidas, reparaciones ni activaciones disponibles.

Para reducir el espacio de búsqueda, los objetos muertos que estén en el suelo se representan mediante una ubicación única o se eliminan de la firma lógica del estado. No se generan sucesores `DROP` ni `PICKUP` destinados únicamente a mover o recuperar un objeto muerto, porque esas acciones no permiten cumplir ninguna condición adicional de la misión y solo aumentan el costo del plan.

Sin embargo, un objeto muerto que todavía está en la carga del robot no se elimina inmediatamente de ella. Su presencia todavía ocupa capacidad y puede hacer necesario hacer un `DROP` para recoger otro objeto. Por lo tanto, se conserva la información de que está en la carga, pero no se considera relevante su ubicación posterior en el suelo. También se permite dejarlo en la zona actual cuando sea necesario liberar espacio.

Esta poda no pierde el costo óptimo de la ruta porque cualquier plan que mueva un objeto muerto entre zonas sin utilizarlo puede transformarse en otro plan que omita esos movimientos y tenga un costo menor o igual. El objeto solo puede conservarse o dejarse cuando su presencia en la carga afecte la capacidad.

Los objetos que aún siguen siendo relevantes para la misión si permanecen completamente representados en el estado. De esta manera, se permite encontrar el plan con el costo óptimo para cumplir la prueba de meta.

---

## Acciones

Defina las acciones **internas** del agente (nombres libres). Para cada una:
precondiciones, efectos, costo. Toda acción del mundo exige además
`batería ≥ costo`.

Puede usar una tabla:

```text
Acción | Precondiciones | Efectos | Costo
```

Las acciones internas representan las operaciones que el agente puede ejecutar sobre el mundo. Toda acción es aplicable únicamente si se cumplen sus
precondiciones y, además, si la batería restante es mayor al costo de la acción.

| Acción | Precondiciones | Efectos | Costo |
|---|---|---|---|
| `MOVER(zona_destino)` | Existe un corredor entre la zona actual y la zona destino. Si el corredor tiene una puerta, esta debe estar abierta. La batería es suficiente. | El robot cambia a `zona_destino` y consume la energía correspondiente al corredor. | Costo oficial del corredor |
| `RECOGER(objeto)` | El objeto está en el suelo de la zona actual y la carga todavía tiene espacio disponible. La batería es suficiente. | El objeto pasa del suelo a `carga_robot`. Si es un material, disminuye en uno la cantidad disponible en el suelo. | El costo de recoger objetos definido en el escenario |
| `DEJAR(objeto)` | El objeto está en `carga_robot` y la batería es suficiente. Durante la búsqueda, la acción debe ser relevante para el plan. | El objeto sale de la carga y queda en el suelo de la zona actual. | El costo de dejar objetos definido en el escenario |
| `ABRIR_PUERTA(puerta)` | El robot está en una de las zonas conectadas por la puerta, la puerta está cerrada y la llave correspondiente está en la carga. La batería es suficiente. | La puerta pasa a estar abierta. La llave permanece en la carga porque no se consume. | El costo de interactuar con el entorno |
| `REPARAR_PANEL(panel)` | El robot está en la zona del panel, el panel está dañado y la carga contiene la herramienta y el material requeridos. La batería es suficiente. | El panel pasa a estar reparado, se consume una unidad del material y la herramienta permanece disponible. | El costo de interactuar con el entorno |
| `ACTIVAR_ESTACION(estacion)` | El robot está en la zona de la estación, esta se encuentra `OFFLINE` y se cumplen todas sus dependencias: paneles reparados y estaciones activadas. La batería es suficiente. | La estación pasa a estar `ONLINE`. | El costo de interactuar con el entorno |
| `RECARGAR(cargador)` | El robot está en la zona del cargador, la batería no está llena y hay energía suficiente para pagar la recarga. | Primero se descuenta el costo de la recarga y después la batería vuelve a su capacidad máxima. | El costo de recargar definido en el escenario |

Restricción de `DEJAR` (`DROP`)

Aunque el contrato permite dejar un objeto en cualquier zona, el agente no genera todas esas posibilidades durante la búsqueda. Hacerlo produciría muchas configuraciones que solo se diferencian por la ubicación de los objetos y aumentaría innecesariamente el espacio que debe explorar.

El agente solo genera `DEJAR` cuando:

- Necesita liberar espacio para recoger un objeto importante.
- Deja el objeto en su zona de origen.
- Deja el objeto en la zona donde será utilizado.
- El objeto ya no es necesario, por ejemplo, una llave cuya puerta ya fue
  abierta.

Los objetos que todavía pueden abrir puertas, reparar paneles o cumplir dependencias se mantienen en el estado. Un objeto que ya no sea útil puede ignorarse respecto a su ubicación en el suelo, aunque si permanece en la carga todavía ocupa espacio y podría ser necesario dejarlo para recoger otro objeto.

### `Applicable` interno vs legalidad del contrato

El simulador dice cuándo un paso es **legal**. Su generador de sucesores dice
qué acciones son **relevantes para buscar**. No tienen que ser el mismo conjunto.

El contrato **permite** `DROP` en cualquier zona si el objeto está en la carga.
Si su agente genera ese `DROP` en cada estado con carga, el espacio deja de ser
«5 zonas y unas tareas» y pasa a ser «en cuál de las 5 zonas quedó cada objeto».
Eso no se arregla cambiando `cargo_capacity` ni apagando la batería: el escenario
es la fuente de verdad y el profesor probará otras instancias.

Usted puede (y se espera que) restrinja `DROP` —y cualquier otra acción— a los
casos que un plan **óptimo** podría necesitar. Justifique que ningún plan de
costo mínimo usa una acción que usted dejó de generar.

(completar: en particular, cuándo genera `DROP` y por qué)

---

## Modelo de transición

```text
s  --a-->  s'     solo si a ∈ Applicable(s)
```

`Result` es determinista y parcial. Qué puede cambiar: zona, carga/suelo,
batería, entorno persistente. Qué se preserva. Si canonicaliza el estado tras
una acción, dígalo aquí.

(completar)

---

## Prueba de meta

```text
Goal(s) ⟺ …
```

La misión se verifica sobre el **estado final del mundo**, no sobre haber
ejecutado una lista de tareas. ¿Las puertas y los paneles son parte de la meta
o solo medios?

(completar)

---

## Función de costo

```text
g(n) = …
```

Debe ser la suma de los **costos oficiales** del escenario (no el número de
pasos). Explique por qué minimizar pasos no es lo mismo que minimizar costo
en este mundo (hay corredores baratos y caros).

(completar)

---

## Estrategia de búsqueda

Elija una estrategia **vista en clase** y justifíquela con las propiedades
reales del problema (costos heterogéneos, plan de menor costo, espacio finito).

Discuta:

- completitud
- optimalidad (¿la prueba de meta se hace al extraer o al generar?)
- costo de camino
- tiempo y espacio (el `b` peligroso no es el grado del mapa: es cuántos
  `DROP`/`PICKUP` genera por estado)
- cuándo se rompen las garantías (costos 0 o negativos, estados mal
  canonicalizados, OPEN que no se vacía)

Graph Search exige una lista CLOSED sobre estados **canónicos**. Explique cómo
evita reexplorar la misma situación física.

(completar)

### Batería como recurso

La batería **sí** va en el estado (§2.1). Eso no implica explorar todos los
paseos que solo gastan energía. Si dos caminos llegan a la **misma**
configuración del mundo (zona, carga, suelo, entorno) y uno trae **más batería
residual** a un **costo menor o igual**, el otro no puede mejorar ningún plan
futuro: está dominado. Tratar cada nivel de batería como un mundo distinto,
sin esa observación, hace que UCS recorra detours inútiles hasta agotar
memoria. Justifique cómo CLOSED aprovecha (o no) esta dominancia.

(completar)

---

## Formulación y tamaño del espacio (obligatorio)

El mapa visible es pequeño. El espacio de estados **no** lo es, si se formula
mal. Responda con sus palabras:

1. ¿Por qué «5 zonas, ~10 objetos, capacidad 3» puede generar millones de nodos
   en un UCS ingenuo?
2. ¿Qué papel tiene `DROP` en esa explosión?
3. ¿Qué podas o abstracciones aplicó y por qué **no pierden el óptimo**
   (*sound*)?
4. ¿Por qué **no** es solución subir la capacidad, bajar las estaciones o
   ignorar la batería?

(completar)
