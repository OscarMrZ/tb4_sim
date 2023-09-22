import os
import pathlib
import launch
import xacro
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch.substitutions.path_join_substitution import PathJoinSubstitution
from launch_ros.actions import Node
from webots_ros2_driver.urdf_spawner import URDFSpawner, get_webots_driver_node
from webots_ros2_driver.webots_launcher import WebotsLauncher, Ros2SupervisorLauncher

def get_ros2_nodes(*args):

    # Parameters
    package_dir = get_package_share_directory('tb4_sim')
    tb4_xacro_path = os.path.join(package_dir, 'resource', 'tb4_webots.xacro')
    tb4_description = xacro.process_file(tb4_xacro_path, mappings={'name': 'turtlebot4'}).toxml()
    ros2_control_params = os.path.join(package_dir, 'resource', 'tb4_control.yaml')
    
    # URDF spawner
    spawn_URDF_tb4 = URDFSpawner(
        name='turtlebot4',
        robot_description=tb4_description,
        relative_path_prefix=os.path.join(package_dir, 'resource'),
        translation='0 0 0',
        rotation='0 0 1 -1.5708',
    )

    # Remaps
    mappings = [('/diffdrive_controller/cmd_vel_unstamped', '/cmd_vel')]
    if 'ROS_DISTRO' in os.environ and os.environ['ROS_DISTRO'] in ['humble', 'rolling']:
        mappings.append(('/diffdrive_controller/odom', '/odom'))

    # Driver nodes
    tb4_driver = Node(
        package='webots_ros2_driver',
        executable='driver',
        output='screen',
        additional_env={'WEBOTS_CONTROLLER_URL': 'turtlebot4'},
        parameters=[
            {'robot_description': tb4_description,
             'use_sim_time': True,
             'set_robot_state_publisher': True},
            ros2_control_params
        ],
        remappings=mappings
    )

    # Other ros2 nodes
    # TODO: Revert once the https://github.com/ros-controls/ros2_control/pull/444 PR gets into the release
    controller_manager_timeout = ['--controller-manager-timeout', '75']
    controller_manager_prefix = 'python.exe' if os.name == 'nt' else ''

    # Diffdrive controller spawner
    diffdrive_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        output='screen',
        prefix=controller_manager_prefix,
        arguments=['diffdrive_controller'] + controller_manager_timeout,
    )

    joint_state_broadcaster_spawner = Node(
        package='controller_manager',
        executable='spawner',
        output='screen',
        prefix=controller_manager_prefix,
        arguments=['joint_state_broadcaster'] + controller_manager_timeout,
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': '<robot name=""><link name=""/></robot>'
        }],
    )

    footprint_publisher = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        output='screen',
        arguments=['0', '0', '0', '0', '0', '0', 'base_link', 'base_footprint'],
    )

    return [
        # Request the spawn of the URDF robot
        spawn_URDF_tb4,

        # Other ros2 nodes
        joint_state_broadcaster_spawner,
        diffdrive_controller_spawner,
        robot_state_publisher,
        footprint_publisher,

        # Launch the driver node once the URDF robot is spawned.
        # You might include other nodes to start them with the driver node.
        launch.actions.RegisterEventHandler(
            event_handler=launch.event_handlers.OnProcessIO(
                target_action=spawn_URDF_tb4,
                on_stdout=lambda event: get_webots_driver_node(event, [tb4_driver]),
            )
        ),
    ]

def generate_launch_description():
    package_dir = get_package_share_directory('tb4_sim')
    world = LaunchConfiguration('world')

    # Starts Webots
    webots = WebotsLauncher(
        world=PathJoinSubstitution([package_dir, 'worlds', world]),
        ros2_supervisor=True
    )

    # Starts the Ros2Supervisor node, with by default respawn=True
    ros2_supervisor = Ros2SupervisorLauncher()

    return LaunchDescription([
        DeclareLaunchArgument(
            'world',
            default_value='house.wbt',
            description='Choose one of the world files from `/webots_ros2_universal_robot/worlds` directory'
        ),
        webots,
        
        webots._supervisor, 

        # This action will kill all nodes once the Webots simulation has exited
        launch.actions.RegisterEventHandler(
            event_handler=launch.event_handlers.OnProcessExit(
                target_action=webots,
                on_exit=[launch.actions.EmitEvent(event=launch.events.Shutdown())],
            )
        ),

    ] + get_ros2_nodes())
