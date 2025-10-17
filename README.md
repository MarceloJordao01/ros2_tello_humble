# tello_ros2_stack

Esse é o repositorio principal do tello para as tasks da robocup.

Execute todos os comandos a partir da raiz desse diretorio e lembre de clonar esse workspace recursivamente


## Explicação da organização do repositorio

O repositorio é organizado da seguinte forma:
```bash
docker/
 ├── Dockerfile
 ├── Dockerfile.gpu
modules/
 ├── ros2_shared/
 ├── tello_fase_1/
 ├── tello_ros/
build.sh
exec.sh
run.sh
```

A pasta `docker` contem a imagem para ser usada durante a simulação e para o hardware real. Ela usa como base uma imagem `ros2_humble` e prepara um workspace (com nome de `tello_ros_ws` ) onde todos os arquivos colocados dentro de `modules` são colados dentro de `tello_ros_ws/src`.
A pasta `modules` é usada para armazenar todos os pacotes usados para a execução das tasks com o tello.

#### Sobre os submodulos
- O submodulo `tello_ros` é o driver que viabiliza a comunicação do conteiner com o tello, nele os serviços como `tello_action` e imagem da camera são iniciados, bem como a simulação do tello
- O Submodulo `ros2_shared` atua como dependencia do `tello_ros`
- O Submodulo `tello_fase_1` atua como coleção de pacotes para a execução da fase 1. Nesse conjunto de repositorio temos:
    - `tello_main` esse pacote faz a função de mandar o tello ir para posições predefinidas (usando o serviço `tello_action` com o comando `go`)
    - `base_detectio` esse pacote pega a imagem da camera voltada para baixo (a espcam acoplada) e envia como publisher as bounding box das bases localizadas
    - `base_localization` esse pacote pega as bounding box do `base_detection` e converte para a posição real da arena (Bom pelo menos essa é a ideia)


## Build da imagem
para o build

```bash
./build.sh
```
O nome configurado por padrão para a imagem é `tello_ros2_humble`

## Execução da imagem
para o run
```bash
./run.sh
```
Esse run já vincula a pasta modules a pasta src dentro do conteiner, ou seja, toda mudança nos pacotes de modules vai refletir no conteiner sem precisar refazer o build.

dar exec
```bash
./exec.sh
```

### Executar a simulação

#### Simulação do tello simples

Dentro do conteiner

```bash
ros2 launch tello_gazebo simple_launch.py
```
Essa simulação apenas sobe o tello e os serviços ligados a ele

comandos do tello simulado
```bash
ros2 service call /drone1/tello_action tello_msgs/TelloAction "{cmd: 'takeoff'}"
ros2 service call /drone1/tello_action tello_msgs/TelloAction "{cmd: 'rc vx vy vz vyaw'}"
ros2 service call /drone1/tello_action tello_msgs/TelloAction "{cmd: 'go dx dy dz speed'}"
ros2 service call /drone1/tello_action tello_msgs/TelloAction "{cmd: 'land'}"
```
Mais sobre a explicação dos serviços no repositorio [tello_ros](https://github.com/MarceloJordao01/tello_ros)


#### Executar simulação para fase 1

```bash
ros2 launch tello_main sim.launch.py
```

Essa simulação roda o gazebo, navigator e o rviz. Ao iniciar a simulação, o tello não irá para os waypoints designados, ele só irá seguir a rota de waypoints depois da chamada do serviço `/tello_navigator/start_auto` descrita no comando abaixo

```bash
ros2 service call /tello_navigator/start_auto std_srvs/srv/Trigger "{}"
```


#### Executar o arquivo de calibração dentro do conteiner
n é o numero de amostras
w é o intervalo de tempo de registro da amostra (do inicio da simulação ate ficar parado)
use-rviz é para abrir o rviz ou não

```bash
python3 /tello_ros_ws/batch_calib_runner.py -n 100 -w 28 --use-rviz false
```