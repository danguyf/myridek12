# My Ride K-12 Home Assistant Integration

A Home Assistant custom component integration for **Tyler Technologies' My Ride K-12** platform.

Tracks school bus location and distance to student bus stop / home during user-configured active hours. (Defaults to between **6:00 AM and 8:00 AM**.)

---

## Features

- 🚌 **School Bus Distance Sensor**: Creates a Home Assistant entity per student (e.g. `sensor.school_bus_distance_zachary`) displaying distance in miles or kilometers.
- ⏰ **Active Window Polling**: Monitors bus location only during user-configured active hours. (Defaults to between **6:00 AM and 8:00 AM** on school days).
- 🔑 **Automatic AWS Cognito Auth**: Authenticates securely using your My Ride K-12 portal credentials.
- 📍 **Bus Stop & Route Metadata**: Exposes detailed entity attributes:
  - Student Name & School
  - Scheduled Bus Number & Active Vehicle Number
  - Route / Run Name & Driver Name
  - Bus Stop Address, Latitude, Longitude
  - Last Scan Time & Scan Status
  - Active Window Status

---

## Installation

### Method 1: Manual Installation

1. Copy the `custom_components/myridek12` directory into your Home Assistant configuration directory:
   ```bash
   cp -r custom_components/myridek12 /config/custom_components/
   ```
2. Restart Home Assistant.

### Method 2: HACS (Custom Repository)

1. Open **HACS** > **Integrations**.
2. Click the three dots (top right) > **Custom repositories**.
3. Add repository URL `https://github.com/danguyf/myridek12` with category **Integration**.
4. Click **Download** and restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **My Ride K-12**.
3. Enter your login credentials.
4. Click **Submit**.

### Options & Customization

Click **Configure** on the My Ride K-12 integration card to customize:
- **Start Hour**: Default `6` (6:00 AM)
- **End Hour**: Default `8` (8:00 AM)
- **Weekdays Only**: Default `True` (Mon - Fri)
- **Distance Unit**: `mi` (Miles) or `km` (Kilometers)

---

## Sensor Entities & Attributes

A dedicated sensor entity is automatically created for **each child** associated with your My Ride K-12 account:
- Entity Name format: `School Bus Distance <FirstName><LastName>` (e.g. `School Bus Distance ZacharySmith`)
- Entity ID format: `sensor.school_bus_distance_<firstname><lastname>` (e.g. `sensor.school_bus_distance_zacharysmith`)

### Example Sensor: `sensor.school_bus_distance_zacharysmith`
- **State**: Distance in miles/km (e.g. `1.31`), or `Inactive` outside active monitoring hours.
- **Attributes**:
  ```yaml
  distance
  status
  student_name
  student_id
  school_name
  bus_number
  active_vehicle
  route_name
  driver_name
  stop_location
  stop_latitude
  stop_longitude
  active_window
  active_window_hours
  ```

---

## Verification Test

To verify connectivity and test data extraction locally:
```bash
python3 test_integration.py <email> <password>
# or
MYRIDEK12_USERNAME=your_email MYRIDEK12_PASSWORD=your_password python3 test_integration.py
```
