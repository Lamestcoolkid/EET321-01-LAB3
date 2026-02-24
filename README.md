# EET321-01-LAB3
EET321 Measurement and Test  ELECTRONICS LAB

Lab 3: Characterizing an SCR using Automated Test Equipment 
Objective:
The objective of this lab is to characterize the on-time of an SCR (silicon controlled rectifier) circuit using both manual measurements and an automated test routine. Students will set up a circuit with an SCR, use test equipment to measure on-time over a range of resistor values, develop algorithms to calculate on-time, and automate the test process using a microcontroller development board.  
 
Equipment:
- SCR (C106 or similar)
- Resistors (including high power 100Ohm resistor)
- Digital potentiometer (10kΩ) model DS1804-010
- Oscilloscope (100MHz or better)
- DMM  
- DC Power supply
- Transformer (6VAC output)
- Microcontroller development board (Arduino, Pi, etc.)
Procedure:
1. Construct the circuit shown in Figure 1 on a breadboard using the provided components. 
 
 <img width="738" height="325" alt="image" src="https://github.com/user-attachments/assets/1ba35e12-2d20-4e43-a337-f7430391f9f9" />

NOTE: Use Blue connections instead of Yellow to avoid overloading R1

2. Manually adjust R4 over its full range and measure the SCR on time at each setting using the oscilloscope. Record this data.
 
3. Develop an algorithm to accurately calculate on-time based on the oscilloscope waveform. Consider defining on-time as the interval between when the voltage first drops to 0V to when it reaches its negative peak.  
 
4. Interface the digital potentiometer to the microcontroller development board. Write code to step through each wiper position (0-99) and record the SCR on-time at each step.  
 
5. Compare the data from automated measurements to the manual measurements. Evaluate sources of error.
 
6. Calculate the ideal resistance value at each wiper position based on the digital potentiometer data sheet. Compare measured values to ideal values and calculate tolerance deviations. 
 
Analysis:
- Plot SCR on-time versus resistance for both manual and automated measurements. Compare trends.
- Evaluate the tolerance deviation analysis. Was the digital potentiometer within expected tolerance ranges? 
- Determine if there is any correlation between the worst-case resistance deviations and worst-case on-time deviations.
 
Conclusions:
Summarize the key findings regarding SCR on-time behavior and the performance of the digital potentiometer under test.
 
Lab Report:
Use the data collected and analysis performed to generate a complete lab report detailing the objective, equipment, procedure, results, discussion, and conclusions of the experiment. Follow the attached report format.


Lead Group Presentation 
The Lead group for the lab is responsible for collecting data from all groups and creating a comprehensive presentation of the class data.  Compare results between groups showing correlation and potential conflicting data. Be prepared to discuss results and conclusions with the whole class.


