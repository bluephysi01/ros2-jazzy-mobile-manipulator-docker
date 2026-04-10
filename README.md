# ROS 2 Jazzy Mobile Manipulator Project

이 저장소는 Docker를 활용한 ROS 2 Jazzy 개발 환경 구축 및 로봇 매니퓰레이션 시뮬레이션 환경을 빠르고 쉽게 구축하기 위한 가이드와 소스 코드를 제공합니다.

---

## 1. 사전 준비 (GUI 허용)
도커 컨테이너 내부에서 실행되는 그래픽 프로그램(Gazebo, RViz2 등)의 창을 호스트(사용자 PC) 화면에 띄우기 위한 필수 설정입니다. 
컴퓨터 부팅 후 로컬 터미널에서 최초 1회 실행해 주세요.

```bash
xhost +local:docker
```

---

## 2. 프로젝트 다운로드
GitHub에서 소스코드 및 개발 환경에 필요한 도커 파일을 로컬 컴퓨터로 복제(Clone)합니다.

```bash
git clone https://github.com/bluephysi01/ros2-jazzy-mobile-manipulator-docker.git
cd ros2-jazzy-mobile-manipulator-docker
```

---

## 3. 도커 이미지 빌드
제공된 Dockerfile을 사용하여 ROS 2 Jazzy와 시뮬레이션에 필요한 패키지들이 설치된 개발 환경 이미지를 생성합니다.
*(인터넷 환경에 따라 이미지 빌드에 약간의 시간이 소요될 수 있습니다.)*

```bash
sudo docker build -t ros2_jazzy_robot .
```

---

## 4. 컨테이너 생성 및 실행
빌드된 이미지를 기반으로 컨테이너를 생성하고 내부 터미널로 진입합니다.
로컬 호스트의 src 폴더가 컨테이너 내부(/home/root/ros2_jazzy_ws/src)와 동기화(볼륨 마운트)되므로, 컨테이너 외부에서 코드를 수정해도 즉시 반영됩니다.

```bash
sudo docker run -it \
  --name my_robot_container \
  --privileged \
  --network host \
  --env="DISPLAY" \
  --env="LIBGL_ALWAYS_SOFTWARE=1 rviz2" \
  --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
  --volume="$PWD/src:/home/root/ros2_jazzy_ws/src" \
  ros2_jazzy_robot
```

---

## 5. 자주 사용하는 명령어 모음 (Cheatsheet)

### 컨테이너 재접속
작업을 마치고 컨테이너를 종료한 후, 나중에 다시 접속할 때 사용합니다.
```bash
sudo docker start -ai my_robot_container
```

### 새 터미널 창 열기
현재 실행 중인 컨테이너에 새로운 터미널 세션을 추가로 열어 다중 작업을 할 때 사용합니다.
```bash
sudo docker exec -it my_robot_container bash
```

### 소스코드 수정 후 빌드 (컨테이너 내부)
호스트 편집기(VS Code 등)에서 소스 코드를 수정한 뒤, 컨테이너 내부 터미널에서 작업 공간을 빌드하고 적용하는 방법입니다.
```bash
cd /home/root/ros2_jazzy_ws
colcon build --symlink-install
source install/setup.bash
```
