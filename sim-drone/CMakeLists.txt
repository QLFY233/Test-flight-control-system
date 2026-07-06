cmake_minimum_required(VERSION 3.0.2)
project(sim_drone)

# Find catkin and required packages
find_package(catkin REQUIRED COMPONENTS
  rospy
  geometry_msgs
  sensor_msgs
)

# Declare catkin package
catkin_package()

# Install Python scripts
catkin_install_python(PROGRAMS
  scripts/fake_drone_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

# Install launch files
install(DIRECTORY launch/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch
)
