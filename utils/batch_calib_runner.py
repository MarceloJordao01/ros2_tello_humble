#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import signal
import subprocess
import sys
import time
from typing import List, Optional


def run_cmd(cmd: List[str], check: bool = False, capture: bool = False, env=None, timeout: Optional[float] = None):
    """Helper para rodar comandos simples."""
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=capture,
        env=env,
        timeout=timeout,
    )


def service_exists(service_name: str, env=None) -> bool:
    """
    Verifica se um serviço existe usando 'ros2 service list'.
    Compatível com ROS2 Humble (que não tem 'ros2 service wait').
    """
    res = run_cmd(["ros2", "service", "list"], check=False, capture=True, env=env)
    if res.returncode != 0:
        # Sem ROS graph ainda, ou erro; considere que não existe.
        return False
    lines = (res.stdout or "").splitlines()
    return any(line.strip() == service_name for line in lines)


def wait_for_service(service_name: str, timeout_sec: float, poll_interval: float = 0.5, env=None) -> bool:
    """
    Aguarda até o serviço aparecer no grafo ROS2, com timeout.
    """
    print(f"[runner] Aguardando serviço {service_name} ficar disponível (timeout={timeout_sec:.1f}s)...")
    t0 = time.time()
    while True:
        if service_exists(service_name, env=env):
            print("[runner] Serviço disponível.")
            return True
        if (time.time() - t0) >= timeout_sec:
            print("[runner] Timeout aguardando serviço.")
            return False
        time.sleep(poll_interval)


def bool_to_launch_str(value: bool) -> str:
    return "true" if value else "false"


def str2bool(v: str) -> bool:
    return str(v).lower() in ("1", "true", "t", "yes", "y", "on")


def build_launch_cmd(
    base_cmd: List[str],
    use_rviz: bool,
    use_gazebo_gui: bool,
    base_fixed: bool,
    base_x: float | None,
    base_y: float | None,
    base_z: float | None,
    base_yaw: float | None,
) -> List[str]:
    """
    Constrói o comando de launch incluindo as flags suportadas no calib.launch.py.
    """
    cmd = list(base_cmd)
    cmd.append(f"use_rviz:={bool_to_launch_str(use_rviz)}")
    cmd.append(f"use_gazebo_gui:={bool_to_launch_str(use_gazebo_gui)}")
    cmd.append(f"base_fixed:={bool_to_launch_str(base_fixed)}")
    if base_fixed:
        # Só faz sentido enviar quando base_fixed=true
        if base_x is not None:
            cmd.append(f"base_x:={base_x}")
        if base_y is not None:
            cmd.append(f"base_y:={base_y}")
        if base_z is not None:
            cmd.append(f"base_z:={base_z}")
        if base_yaw is not None:
            cmd.append(f"base_yaw:={base_yaw}")
    return cmd


def launch_once(
    launch_cmd: List[str],
    service_name: str,
    wait_before_trigger: float,
    after_trigger_sleep: float,
    shutdown_timeout: float,
    service_wait_timeout: float,
    iteration_env: dict | None = None,
) -> bool:
    """
    Sobe o launch, aguarda, espera serviço aparecer, dispara o serviço, e encerra o launch.
    Retorna True/False conforme sucesso do ciclo.
    """
    env = os.environ.copy()
    if iteration_env:
        env.update(iteration_env)

    print(f"\n[runner] Iniciando: {' '.join(launch_cmd)}")
    proc = subprocess.Popen(
        launch_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid,  # cria um novo grupo de processos no Unix
        env=env,
        bufsize=1,
    )

    try:
        # Espera o warmup fixo antes de procurar o serviço (permite nós subirem)
        t0 = time.time()
        while True:
            if proc.stdout:
                line = proc.stdout.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()

            if (time.time() - t0) >= wait_before_trigger:
                break

            if proc.poll() is not None:
                print("[runner] O launch finalizou antes do tempo de espera; abortando este ciclo.")
                return False

            time.sleep(0.05)

        # Aguarda serviço aparecer (compatível com Humble)
        ok_wait = wait_for_service(service_name, timeout_sec=service_wait_timeout, env=env)
        if not ok_wait:
            ok = False
        else:
            # Dispara o Trigger
            print("[runner] Disparando captura...")
            call_res = run_cmd(
                ["ros2", "service", "call", service_name, "std_srvs/srv/Trigger", "{}"],
                check=False,
                capture=True,
                env=env,
            )
            sys.stdout.write(call_res.stdout or "")
            sys.stdout.write(call_res.stderr or "")
            ok = (call_res.returncode == 0)

        time.sleep(after_trigger_sleep)

    finally:
        # Encerra o launch com SIGINT (equivalente a Ctrl+C)
        try:
            print("[runner] Encerrando launch (SIGINT)...")
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        except ProcessLookupError:
            pass

        # Aguarda término gracioso
        try:
            proc.wait(timeout=shutdown_timeout)
        except subprocess.TimeoutExpired:
            print("[runner] Timeout no desligamento gracioso. Enviando SIGTERM...")
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("[runner] Forçando encerramento (SIGKILL)...")
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Roda calib.launch.py (no pacote tello_main), espera e dispara o serviço de captura, repetindo N vezes."
    )
    parser.add_argument("--iterations", "-n", type=int, default=100,
                        help="Número de iterações (default: 100).")
    parser.add_argument("--wait", "-w", type=float, default=28.0,
                        help="Tempo (s) antes do trigger (default: 28).")
    parser.add_argument("--after-trigger-sleep", "-s", type=float, default=2.0,
                        help="Tempo (s) após o trigger antes de encerrar (default: 2).")
    parser.add_argument("--shutdown-timeout", "-t", type=float, default=15.0,
                        help="Timeout (s) de desligamento gracioso (default: 15).")
    parser.add_argument("--service-wait-timeout", "-T", type=float, default=60.0,
                        help="Timeout (s) para o serviço ficar disponível (default: 60).")
    parser.add_argument("--service", default="/calib_data_logger_posearray/capture_once",
                        help="Serviço Trigger a ser chamado (default: /calib_data_logger_posearray/capture_once).")

    # Flags do launch (calib.launch.py em tello_main)
    parser.add_argument("--use-rviz", default="true",
                        help='Abre o RViz no launch (true/false). Default: "true".')
    parser.add_argument("--use-gazebo-gui", default="false",
                        help='Abre o gzclient (true/false). Default: "false".')
    parser.add_argument("--base-fixed", default="false",
                        help='Posição fixa da base (true/false). Default: "false".')
    parser.add_argument("--base-x", type=float, default=None, help="X fixo quando base-fixed=true.")
    parser.add_argument("--base-y", type=float, default=None, help="Y fixo quando base-fixed=true.")
    parser.add_argument("--base-z", type=float, default=None, help="Z fixo quando base-fixed=true.")
    parser.add_argument("--base-yaw", type=float, default=None, help="Yaw fixo (rad) quando base-fixed=true.")

    # Seeding (controla aleatoriedade do spawn no launch)
    parser.add_argument("--seed", type=int, default=None,
                        help="Define LAND_BASE_SEED. Se omitido, NÃO define a variável (aleatório real).")
    parser.add_argument("--seed-mode", choices=["fixed", "per-iter"], default="per-iter",
                        help='fixed: usa exatamente --seed em todas as iterações; '
                             'per-iter: usa seed+(i-1). Default: per-iter.')

    parser.add_argument(
        "--launch", nargs=argparse.REMAINDER,
        help="Comando de launch completo após '--launch'. Ex.: --launch ros2 launch tello_main calib.launch.py"
    )

    args = parser.parse_args()

    # Comando padrão de launch, caso --launch não seja passado
    base_launch_cmd = args.launch if args.launch else ["ros2", "launch", "tello_main", "calib.launch.py"]

    # Converte flags para bools e injeta no comando
    use_rviz_bool = str2bool(args.use_rviz)
    use_gz_gui_bool = str2bool(args.use_gazebo_gui)
    base_fixed_bool = str2bool(args.base_fixed)

    launch_cmd = build_launch_cmd(
        base_cmd=base_launch_cmd,
        use_rviz=use_rviz_bool,
        use_gazebo_gui=use_gz_gui_bool,
        base_fixed=base_fixed_bool,
        base_x=args.base_x,
        base_y=args.base_y,
        base_z=args.base_z,
        base_yaw=args.base_yaw,
    )

    print("[runner] Configuração:")
    print(f"  Iterações..............: {args.iterations}")
    print(f"  Espera antes do trigger: {args.wait:.1f}s")
    print(f"  Pós-trigger sleep......: {args.after_trigger_sleep:.1f}s")
    print(f"  Shutdown timeout.......: {args.shutdown_timeout:.1f}s")
    print(f"  Service wait timeout...: {args.service_wait_timeout:.1f}s")
    print(f"  Serviço................: {args.service}")
    print(f"  use_rviz...............: {use_rviz_bool}")
    print(f"  use_gazebo_gui.........: {use_gz_gui_bool}")
    print(f"  base_fixed.............: {base_fixed_bool}")
    if base_fixed_bool:
        print(f"    base_x/base_y/base_z/base_yaw: {args.base_x}/{args.base_y}/{args.base_z}/{args.base_yaw}")
    print(f"  seed...................: {args.seed} (mode={args.seed_mode})")
    print(f"  Launch cmd.............: {' '.join(launch_cmd)}")

    successes = 0
    for i in range(1, args.iterations + 1):
        print("\n" + "=" * 70)
        print(f"[runner] Iteração {i}/{args.iterations}")
        print("=" * 70)

        # Controla a semente via env APENAS se --seed foi fornecido.
        iteration_env = None
        if args.seed is not None:
            if args.seed_mode == "fixed":
                seed_val = args.seed
            else:  # per-iter
                seed_val = args.seed + (i - 1)
            iteration_env = {"LAND_BASE_SEED": str(seed_val)}
            print(f"[runner] LAND_BASE_SEED={seed_val}")

        ok = launch_once(
            launch_cmd=launch_cmd,
            service_name=args.service,
            wait_before_trigger=args.wait,
            after_trigger_sleep=args.after_trigger_sleep,
            shutdown_timeout=args.shutdown_timeout,
            service_wait_timeout=args.service_wait_timeout,
            iteration_env=iteration_env,
        )
        if ok:
            successes += 1
            print(f"[runner] Iteração {i}: SUCESSO")
        else:
            print(f"[runner] Iteração {i}: FALHA")

        time.sleep(1.0)

    print("\n" + "-" * 60)
    print(f"[runner] Concluído. Sucessos: {successes}/{args.iterations}")
    print("-" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[runner] Interrompido pelo usuário.")
