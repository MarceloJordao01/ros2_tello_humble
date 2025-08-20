# tello_ros2_stack

para o build

```bash
./build.sh
```

para o run
```bash
./run.sh
```
dar exec
```bash
docker exec -it tello_conteiner bash
```

executar a simulação
```bash
ros2 launch tello_gazebo simple_launch.py
```

comandos do tello simulado
```bash
ros2 service call /drone1/tello_action tello_msgs/TelloAction "{cmd: 'takeoff'}"
ros2 service call /drone1/tello_action tello_msgs/TelloAction "{cmd: 'rc vx vy vz vyaw'}"
ros2 service call /drone1/tello_action tello_msgs/TelloAction "{cmd: 'go dx dy dz speed'}"
ros2 service call /drone1/tello_action tello_msgs/TelloAction "{cmd: 'land'}"
```