project:
  id: "P20260914-001"
  name: "项目名称"
  type: "villa"
  location: "Indonesia"

building_data:
  total_width: 12000
  total_depth_with_yard: 17000
  main_building_depth: 11000
  portico_depth: 4000
  backyard_depth: 2000
  vertical_layout:
    living_room:
      depth: 4200
      width: 5000
    dining_room:
      depth: 3425
      width: 8000
    bedroom:
      depth: 3375
      width: 8000
  horizontal_layout:
    bedroom_dining_zone: 8000
    parking_zone: 3000
    corridor: 2000

stair_bathroom_storage:
  bathroom:
    width: 3000
    depth: 1663
  spiral_stair:
    depth: 1763
    leads_to: "roof_deck"
  storage:
    depth: 1763

photovoltaic:
  enabled: true
  total_panels: 60
  zones:
    main_roof_1: 24
    main_roof_2: 12
    carport: 24
  tilt_angle: 12

incremental_structure:
  enabled: true
  type: "carport_canopy"
  dimensions:
    width: 5000
    depth: 8200
    height_top: 3300

video_generation:
  enabled: true
  duration_seconds: [60, 100]
  resolution: "1920x1080"
  fps: 24

quality_assessment:
  axes:
    - accuracy
    - completeness
    - clarity
    - actionability
    - conciseness
  min_score: 3.5
  max_iterations: 3