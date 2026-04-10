#!/usr/bin/env python3

import time
import threading
import rclpy
import numpy as np
from rclpy.node import Node
from rclpy.logging import get_logger
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Float64MultiArray, String
from moveit.core.robot_state import RobotState
from moveit.planning import MoveItPy
from moveit_msgs.msg import CollisionObject
from shape_msgs.msg import SolidPrimitive
from moveit.core.kinematic_constraints import construct_joint_constraint
from geometry_msgs.msg import Pose

def plan_and_execute(robot, planning_component, logger, sleep_time=0.0):
    logger.info("Planning trajectory")
    plan_result = planning_component.plan()
    if not plan_result:
        logger.error("Planning failed. No valid trajectory generated.")
        return False
    logger.info("Executing plan")
    robot_trajectory = plan_result.trajectory
    if robot_trajectory:
        robot.execute(robot_trajectory, controllers=[])
        time.sleep(sleep_time)
        return True
    else:
        logger.error("Execution failed. No valid trajectory.")
        return False

class Controller(Node):
    def __init__(self):
        super().__init__('commander')
        self.get_logger().info("\n\n\nInitialize Manipulator\n\n\n")

        self.subscription = self.create_subscription(
            Float64MultiArray, '/target_point', self.listener_callback, 10
        )
        self.status_pub = self.create_publisher(String, '/pick_place_status', 10)

        self.pose_goal = PoseStamped()
        self.pose_goal.header.frame_id = "base_link"

        self.ur = MoveItPy(node_name="moveit_py")
        self.get_logger().info("\n\n\nSuccessfully called moveit py node\n\n\n")
        self.ur_arm = self.ur.get_planning_component("ur_manipulator")
        self.ur_hand = self.ur.get_planning_component("robotiq_2f_85_gripper")
        self.logger = get_logger("moveit_py.pose_goal")

        robot_model = self.ur.get_robot_model()
        self.robot_state = RobotState(robot_model)

        # Heights and offsets
        self.backoff_dist = 0.1  # Distance to back off before/after grasping
        self.pick_height = 0.0  # Exactly at object's Z-center
        self.carrying_height = 0.05  # Reduce height to stay inside UR5e reach bounds

        # Forward and horizontally-opening grasping orientation (Pitch=+90, Roll=+90)
        # Forward and horizontally-opening grasping orientation (Pitch=+90, Roll=-90)
        self.side_grasp_orientation = (-0.5, 0.5, -0.5, 0.5)  # (x, y, z, w)
      
        time.sleep(3)

    def publish_status(self, status_msg):
        status = String()
        status.data = status_msg
        self.status_pub.publish(status)
        self.get_logger().info(f"[DEBUG] Publishing pick-place completion: {status_msg}")

    def move_to(self, x, y, z, xo, yo, zo, wo):
        self.pose_goal.pose.position.x = x
        self.pose_goal.pose.position.y = y
        self.pose_goal.pose.position.z = z
        self.pose_goal.pose.orientation.x = xo
        self.pose_goal.pose.orientation.y = yo
        self.pose_goal.pose.orientation.z = zo
        self.pose_goal.pose.orientation.w = wo
        self.ur_arm.set_goal_state(pose_stamped_msg=self.pose_goal, pose_link="tool0")
        return plan_and_execute(self.ur, self.ur_arm, self.logger, sleep_time=2.0)

    def gripper_action(self, action):
        self.ur_hand.set_start_state_to_current_state()
        if action == 'open':
            joint_values = {"robotiq_85_left_knuckle_joint": 0.01}
        elif action == 'close':
            joint_values = {"robotiq_85_left_knuckle_joint": 0.65}
        else:
            self.get_logger().info("No such action")
            return False
        self.robot_state.joint_positions = joint_values
        joint_constraint = construct_joint_constraint(
            robot_state=self.robot_state,
            joint_model_group=self.ur.get_robot_model().get_joint_model_group("robotiq_2f_85_gripper"),
        )
        self.ur_hand.set_goal_state(motion_plan_constraints=[joint_constraint])
        return plan_and_execute(self.ur, self.ur_hand, self.logger, sleep_time=2.0)

    def listener_callback(self, data):
        self.get_logger().info(f"Received target point: {data.data}")
        self.publish_status("IN_PROGRESS")

        start_x, start_y, start_z, start_xo, start_yo, start_zo, start_wo = data.data[0:7]
        goal_x, goal_y, goal_z, goal_xo, goal_yo, goal_zo, goal_wo = data.data[7:14]
        start = (start_x, start_y, start_z)
        goal = (goal_x, goal_y, goal_z)
        valid = True
        
        # Calculate gripper forward vector (Z-axis of tool0) for picking
        dir_sx = 2 * (start_xo*start_zo + start_wo*start_yo)
        dir_sy = 2 * (start_yo*start_zo - start_wo*start_xo)
        dir_sz = (start_wo*start_wo - start_xo*start_xo - start_yo*start_yo + start_zo*start_zo)
        
        # tool0 target pos for grasping
        gripper_len = 0.15
        base_start_x = start_x - dir_sx * gripper_len
        base_start_y = start_y - dir_sy * gripper_len
        base_start_z = start_z + self.pick_height - dir_sz * gripper_len
        
        # Backoff pos for picking (move back along gripper axis)
        start_backoff_x = base_start_x - dir_sx * self.backoff_dist
        start_backoff_y = base_start_y - dir_sy * self.backoff_dist
        start_backoff_z = base_start_z - dir_sz * self.backoff_dist + self.carrying_height

        self.get_logger().info("Moving to backoff position")
        valid = valid and self.move_to(start_backoff_x, start_backoff_y, start_backoff_z, start_xo, start_yo, start_zo, start_wo)

        self.get_logger().info("Opening gripper")
        valid = valid and self.gripper_action("open")

        self.get_logger().info("Moving to pick position")
        valid = valid and self.move_to(base_start_x, base_start_y, base_start_z, start_xo, start_yo, start_zo, start_wo)

        self.get_logger().info("Grasping object")
        valid = valid and self.gripper_action("close")

        self.get_logger().info("Backing up after grasp")
        valid = valid and self.move_to(start_backoff_x, start_backoff_y, start_backoff_z, start_xo, start_yo, start_zo, start_wo)

        # Calculate gripper forward vector for placing
        dir_gx = 2 * (goal_xo*goal_zo + goal_wo*goal_yo)
        dir_gy = 2 * (goal_yo*goal_zo - goal_wo*goal_xo)
        dir_gz = (goal_wo*goal_wo - goal_xo*goal_xo - goal_yo*goal_yo + goal_zo*goal_zo)
        
        base_goal_x = goal_x - dir_gx * gripper_len
        base_goal_y = goal_y - dir_gy * gripper_len
        base_goal_z = goal_z + self.pick_height - dir_gz * gripper_len

        goal_backoff_x = base_goal_x - dir_gx * self.backoff_dist
        goal_backoff_y = base_goal_y - dir_gy * self.backoff_dist
        goal_backoff_z = base_goal_z - dir_gz * self.backoff_dist + self.carrying_height

        self.get_logger().info("Moving to goal backoff position")
        valid = valid and self.move_to(goal_backoff_x, goal_backoff_y, goal_backoff_z, goal_xo, goal_yo, goal_zo, goal_wo)

        self.get_logger().info("Lowering to place position")
        valid = valid and self.move_to(base_goal_x, base_goal_y, base_goal_z, goal_xo, goal_yo, goal_zo, goal_wo)

        self.get_logger().info("Releasing object")
        valid = valid and self.gripper_action("open")

        self.get_logger().info("Backing up after place")
        valid = valid and self.move_to(goal_backoff_x, goal_backoff_y, goal_backoff_z, goal_xo, goal_yo, goal_zo, goal_wo)

        self.get_logger().info("Returning to safe Ready position for driving")
        self.ur_arm.set_goal_state(configuration_name="ready")
        valid = valid and plan_and_execute(self.ur, self.ur_arm, self.logger, sleep_time=2.0)

        if valid:
            self.publish_status("DONE")
        else:
            self.publish_status("FAILED")

if __name__ == '__main__':
    rclpy.init(args=None)
    controller = Controller()
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(controller)
    executor_thread = threading.Thread(target=executor.spin, daemon=True)
    executor_thread.start()
    rate = controller.create_rate(2)
    try:
        while rclpy.ok():
            rate.sleep()
    except KeyboardInterrupt:
        pass
    rclpy.shutdown()
    executor_thread.join()