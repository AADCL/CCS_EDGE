cmake_minimum_required(VERSION 3.0.2)
project(epgeneral_relocalization)

find_package(catkin REQUIRED COMPONENTS epgeneral_device_config geometry_msgs map_server rospy std_msgs tf2_ros)
catkin_python_setup()
catkin_package(CATKIN_DEPENDS epgeneral_device_config geometry_msgs map_server rospy std_msgs tf2_ros)

catkin_install_python(PROGRAMS
  scripts/epgeneral_relocalization_node.py
  scripts/check_version.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
install(DIRECTORY launch DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})

# Enabled only for UGV_004; dependencies come from its read-only underlay.
option(CCS_BUILD_WHEELTEC_LOCALIZER "Build the UGV_004 NDT backend" OFF)
if(CCS_BUILD_WHEELTEC_LOCALIZER)
  find_package(catkin REQUIRED COMPONENTS roscpp tf tf_conversions tf2_ros
    geometry_msgs sensor_msgs nav_msgs std_msgs std_srvs visualization_msgs
    message_filters pcl_ros pcl_conversions fast_lio_localization)
  find_package(PCL REQUIRED)
  find_package(OpenMP REQUIRED)
  add_library(ccs_wheeltec_ndt wheeltec/src/pclomp/ndt_omp.cpp wheeltec/src/pclomp/voxel_grid_covariance_omp.cpp)
  add_executable(ccs_wheeltec_localizer wheeltec/src/fast_lio_localization.cpp)
  foreach(target ccs_wheeltec_ndt ccs_wheeltec_localizer)
    target_compile_features(${target} PRIVATE cxx_std_14)
    target_include_directories(${target} PRIVATE wheeltec/include ${catkin_INCLUDE_DIRS} ${PCL_INCLUDE_DIRS})
    target_compile_options(${target} PRIVATE ${OpenMP_CXX_FLAGS})
    target_link_libraries(${target} ${catkin_LIBRARIES} ${PCL_LIBRARIES} ${OpenMP_CXX_FLAGS})
    add_dependencies(${target} ${catkin_EXPORTED_TARGETS})
  endforeach()
  target_link_libraries(ccs_wheeltec_localizer ccs_wheeltec_ndt)
  if(CATKIN_ENABLE_TESTING)
    add_executable(ccs_wheeltec_gate_test wheeltec/test/test_gate.cpp)
    target_compile_features(ccs_wheeltec_gate_test PRIVATE cxx_std_14)
    target_compile_options(ccs_wheeltec_gate_test PRIVATE -UNDEBUG)
    target_include_directories(ccs_wheeltec_gate_test PRIVATE wheeltec/include)
    add_test(NAME ccs_wheeltec_gate COMMAND ccs_wheeltec_gate_test)
  endif()
  install(TARGETS ccs_wheeltec_ndt ccs_wheeltec_localizer
    ARCHIVE DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION}
    LIBRARY DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION}
    RUNTIME DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
endif()
install(DIRECTORY wheeltec/ DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/wheeltec
  FILES_MATCHING PATTERN "LICENSE" PATTERN "NOTICE.md")
