%% Simulations for intensity field and thermal effects by TUS.
% Version 3 By Xin
% In this version, the real stucture of CTX500 which contains four
% elements, were used for simulation. The phase of the four elements were
% determined by the test report.
close all; clear all;
cd(uigetdir)
%% define model
% load model
brain_model = load('TUS_brain_clean.mat'); 
model = brain_model.Brain_data_clean;
undersample_rate = 1;
% resize & visualization
model = round(imresize3(model, undersample_rate));
% model = model(:,:,35:121);
model = model(:,15:end,20:end);
% pad model
pad_size = [20, 20; 0, 30; 0, 20];
model = pad_model(model, pad_size);

%%

% volumeViewer(model);
[Nx, Ny, Nz] = size(model);
slice = squeeze(model(round(Nx/2)+10,:,:));
img_ratio = size(slice, 2) / size(slice, 1);
figure('Units', 'pixels', 'Position', [50, 50, 700 * img_ratio, 700]);
imagesc(slice);

% create the computational grid
% [Nx, Ny, Nz] = size(model);   % number of grid points in the X/Y direction
dx = 1.5e-3 / undersample_rate;                % grid point spacing in the X direction [m]
dy = 1.5e-3 / undersample_rate;                % grid point spacing in the Y direction [m]
dz = 1.5e-3 / undersample_rate;                % grid point spacing in the Z direction [m]
kgrid = kWaveGrid(Nx, dx, Ny, dy, Nz, dz);

% define the source parameters
freq = 5e5;              % [Hz] 500KHz
roc = 63.2e-3;	% bowl radius of curvature [m]
% aperture diameters of the elements given an inner, outer pairs [m]
diameters = [0 1.28; 1.3 1.802; 1.82 2.19; 2.208 2.52].' * 0.0254;
amp = 7e4;
phase = [0, 331.4, 302.8, 274.2];% focus should be 60 mm
% phase = [0, 296.5, 232.9, 169.4];% focus should be 70 mm

%% define parameters
% speed [m/s]
medium.sound_speed = 1500 * ones(Nx, Ny, Nz);           % default
%medium.sound_speed(model==0)=343.0 ;                    % air
medium.sound_speed(model==0)=1504.0;                    % water
% medium.sound_speed(model>=21 & model<=78)=1546.3;       % midbrain
medium.sound_speed(model==5)=1552.5;       % white matter
medium.sound_speed(model==4)=1500.0;      % grey matter
medium.sound_speed(model==3)=1475.0;        % cerebroSpinalFluid
medium.sound_speed(model==2)=2850.0;       % skull
medium.sound_speed(model==1)=1732.0;                  % scalp
% density [Kg/m3]
medium.density = 1000 * ones(Nx, Ny, Nz);               % default
%medium.density(model==0)=1.20;                          % air
medium.density(model==0)=1000;                          % water
% medium.density(model>=21 & model<=78)=1075;             % midbrain
medium.density(model==5)=1050;             % white matter
medium.density(model==4)=1100;            % grey matter
medium.density(model==3)=1000.0;            % cerebroSpinalFluid
medium.density(model==2)=1732.0;           % skull
medium.density(model==1)=1132.0;                      % scalp
% absortion [dB/(MHz^y cm)]
medium.alpha_power = 1.43;                               % default
medium.alpha_coeff = 0.75 * ones(Nx, Ny, Nz);           % default
medium.alpha_mode = 'no_dispersion';
%medium.alpha_coeff(model==0)=1.6;                       % air
medium.alpha_coeff(model==0)=0.03;                      % water
% medium.alpha_coeff(model>=21 & model<=78)=0.6;          % midbrain
medium.alpha_coeff(model==5)=0.21;          % white matter
medium.alpha_coeff(model==4)=0.21;         % grey matter
medium.alpha_coeff(model==3)=0.03;          % cerebroSpinalFluid
medium.alpha_coeff(model==2)=2.7;          % skull
medium.alpha_coeff(model==1)=0.42;         % scalp 

%% define a focused ultrasound transducer
target_points = [round(Nx/2), 86, 21];
% target_points = [60+25, 75, 57];
% target_points = round(target_points*undersample_rate);

source_pos = [round(Nx/2), 131, 49];% original!

% source_pos = [round(Nx/2), 131, 49];% original!
% source_pos = [60+25, 120, 100];
% source_pos = round(source_pos*undersample_rate);

focus_pos = [kgrid.x_vec(target_points(1)), ...
    kgrid.y_vec(target_points(2)), ...
    kgrid.z_vec(target_points(3))];
bowl_pos = [kgrid.x_vec(source_pos(1)), ...
    kgrid.y_vec(source_pos(2)), ...
    kgrid.z_vec(source_pos(3))];

% define source
% source.p_mask = makeBowl([Nx, Ny, Nz], source_pos, ...
%     curvature_grid, aperture_diameter+1, target_points, 'Plot', true);
karray = kWaveArray('SinglePrecision', true);
karray.addAnnularArray(bowl_pos, roc, diameters, focus_pos);
source.p_mask = karray.getArrayBinaryMask(kgrid);

% calculate the time step using an integer number of points per period
sound_speed = 1482;              % [m/s]
ppw = sound_speed / (freq * dx); % points per wavelength
cfl = 0.3;                       % cfl number
ppp = ceil(ppw / cfl);           % points per period
T   = 1 / freq;                  % period [s]
dt  = T / ppp;   

% calculate the number of time steps to reach steady state
t_end = sqrt( kgrid.x_size.^2 + kgrid.y_size.^2 + kgrid.z_size.^2 ) / sound_speed; 
Nt = round(t_end / dt);

% create the time array
kgrid.setTime(Nt, dt);

% define the input signal
source_amp = repmat(amp, [1,4]); % source pressure for the four elements
source_phase = deg2rad(phase);
source_sig = createCWSignals(kgrid.t_array, freq, source_amp, source_phase); % ramp_length=0
source.p = karray.getDistributedSourceSignal(kgrid, source_sig);

figure;
plot(source.p);

% set the sensor mask to cover the entire grid
sensor.mask = zeros(Nx, Ny, Nz);
sensor.mask(:, :, :) = 1;
sensor.record = {'p', 'p_max','I', 'I_avg'};

% visualization position
visualization_mask = zeros(Nx, Ny, Nz);
visualization_mask(source.p_mask==1)=1;                
visualization_mask(model==1)=2;
% visualization_mask(60,121,27)=3;
volumeViewer(visualization_mask);

% record the last 3 cycles in steady state
num_periods = 3;
T_points = round(num_periods * T / kgrid.dt);
sensor.record_start_index = Nt - T_points + 1;

% set the input arguements
input_args = {'PlotPML', false, 'DisplayMask', ...
    source.p_mask, 'PlotScale', [-1, 1] * amp, 'Smooth', [false, true, true], ...
    'DataCast', 'off'};% 'gpuArray-single'
% input_args = {'PlotPML', false, 'DisplayMask', ...
%     source.p_mask, 'PlotScale', [-1, 1] * amp, 'Smooth', [false, true, true]};

%% run the acoustic simulation
sensor_data = kspaceFirstOrder3D(kgrid, medium, source, sensor, input_args{:});

%% get p data
p = extractAmpPhase(gather(sensor_data.p), 1/kgrid.dt, freq, ...
        'Dim', 2, 'Window', 'Rectangular', 'FFTPadding', 1);
%% =========================================================================
figure;
imagesc(squeeze(medium.density(round(Nx/2),:,:)));
ylabel('x-position [mm]');
xlabel('y-position [mm]');
colormap(jet(256));
c = colorbar;
ylabel(c, 'Density [kg/m^3]');
axis image;
title('Density');

% =========================================================================
figure;
imagesc(squeeze(source.p_mask(round(Nx/2),:,:)) .* 1000);
ylabel('x-position [mm]');
xlabel('y-position [mm]');
colormap(gray);
colorbar;
axis image;
title('Transducer');

% % Save transducer mask
% p_mask = source.p_mask;
% filename_td = sprintf('Transducer_mask_c%.0f.mat',curvature_grid);
% save(filename_td,'p_mask','-v7.3');

% =========================================================================
figure;
Iz_avg_tmp = reshape(sensor_data.Iy_avg, [Nx,Ny,Nz]);
imagesc(abs(squeeze(Iz_avg_tmp(round(Nx/2),:,:))));
ylabel('x-position [mm]');
xlabel('y-position [mm]');
title(['Avg Ix: ',num2str(max(Iz_avg_tmp(:))),'[W/m2]']);
colormap(jet(256));
c = colorbar;
ylabel(c, 'Sound Intensity [W/m2]');
axis image;

% =========================================================================
figure;
Iz_max_tmp = reshape(max(sensor_data.Iz'), [Nx,Ny,Nz]);
imagesc(squeeze(Iz_max_tmp(round(Nx/2),:,:)));
ylabel('x-position [mm]');
xlabel('y-position [mm]');
title(['Max sound intensity Iz: ',num2str(max(Iz_max_tmp(:))),' [W/m2]']);
colormap(jet(256));
c = colorbar;
ylabel(c, 'Sound Intensity [W/m2]');
axis image;

% =========================================================================
figure;
Iz_max_tmp = reshape(sensor_data.p_max, [Nx,Ny,Nz]);
imagesc(squeeze(Iz_max_tmp(round(Nx/2),:,:)));
ylabel('x-position [mm]');
xlabel('y-position [mm]');
title(['Max sound pressure: ',num2str(max(Iz_max_tmp(:))),' [Pa]']);
colormap(jet(256));
c = colorbar;
ylabel(c, 'Sound Pressure [Pa]');
axis image;

% =========================================================================
figure;
Iz_max_tmp = reshape(sensor_data.p_max, [Nx,Ny,Nz]);
Isppa = Iz_max_tmp .^2 ./ (2 .* medium.density .* medium.sound_speed);
imagesc(squeeze(Isppa(round(Nx/2),:,:)));
ylabel('x-position [mm]');
xlabel('y-position [mm]');
title(['Isppa from max pressure: ',num2str(max(Isppa(:))),' [W/m2]']);
colormap(jet(256));
c = colorbar;
ylabel(c, 'Isppa [Pa]');
axis image;

% =========================================================================
figure;
Iz_max_tmp = reshape(p, [Nx,Ny,Nz]);
Isppa = Iz_max_tmp .^2 ./ (2 .* medium.density .* medium.sound_speed);
imagesc(squeeze(Isppa(round(Nx/2),:,:)));
ylabel('x-position [mm]');
xlabel('y-position [mm]');
title(['Isppa: ',num2str(max(Isppa(:))),' [W/m2]']);
colormap(jet(256));
c = colorbar;
ylabel(c, 'Isppa [Pa]');
axis image;

% =========================================================================
% display some information
p = reshape(sensor_data.Iy_avg, [Nx,Ny,Nz]);
[max_pressure, idx] = max(abs(p(:))); % [Pa]
[mx, my, mz] = ind2sub(size(p), idx);
disp(['Maximum I_avg: ' num2str([gather(mx) gather(my) gather(mz)]) ]);

% =========================================================================
% Overlap the figures
figure;
ax1 = axes; imagesc(ax1, imrotate(slice,90));
hold all;
ax2 = axes;
im2 = imagesc(ax2, imrotate(squeeze(Isppa(round(Nx/2),:,:))*1e-4,90));
im2.AlphaData = 0.5;
ax3 = axes;
im3 = imagesc(ax3, imrotate(squeeze(source.p_mask(round(Nx/2),:,:)),90));
im3.AlphaData = 0.1;

linkaxes([ax1,ax2,ax3]); ax2.Visible = 'off'; ax2.XTick = []; ax2.YTick = [];
ax3.Visible = 'off'; ax3.XTick = []; ax3.YTick = [];
colormap(ax1,'gray')
%     colormap(ax2,'turbo')
set([ax1,ax2,ax3],'Position',[.17 .11 .685 .815]);
cb2 = colorbar(ax2,'Position',[.85 .11 .0275 .815]);
xlabel(cb2, '[W/cm2]');
title(ax1,'Acoustic Pressure Amplitude')

%%
% =========================================================================
% CALCULATE HEATING
% =========================================================================
% check input pulse parameters
pulse_dur = 0.03;	% pulse length [s]
pulse_rep_int = 0.1;     % pulse repetition interval [s]
pulse_train_dur = 40;

% convert the absorption coefficient to nepers/m
alpha_np = db2neper(medium.alpha_coeff, medium.alpha_power) * ...
    (2 * pi * freq).^medium.alpha_power;

p = reshape(p, Nx, Ny, Nz);
Q = alpha_np .* abs(reshape(sensor_data.Iz_avg, [Nx,Ny,Nz]));
% p = sqrt(abs(reshape(sensor_data.Iz_avg, [Nx,Ny,Nz])) .* medium.density .* medium.sound_speed);
% reshape the data, and calculate the volume rate of heat deposition
% Q = alpha_np .* p.^2 ./ (medium.density .* medium.sound_speed);

% clear the input structures
clear source sensor;
dens_bone = 1400;

% set the background temperature and heating term
source.Q = Q;

source.T0 = zeros(size(medium.density));
source.T0(:) = 37;

% define medium properties related to diffusion
% based on Verhagen et al., Elife, 2019
medium.thermal_conductivity = zeros(size(medium.density));
medium.thermal_conductivity(medium.density <  1010)  = 0.5;    % water 0.5 
medium.thermal_conductivity(medium.density >= 1010 & medium.density < 1150)  = 0.528; % soft tisue 0.528
medium.thermal_conductivity(medium.density >  dens_bone)  = 0.4;     % bone  0.4

medium.specific_heat = zeros(size(medium.density));     % [J/(kg.K)]
medium.specific_heat(:) = 3600;     % [J/(kg.K)]     (soft tissue/water)
medium.specific_heat(medium.density >  dens_bone) = 1300;     % [J/(kg.K)]     (bone)

medium.blood_density = zeros(size(medium.density));
medium.blood_density((medium.density >= 1010 & medium.density <= dens_bone))  = 1030;   % [kg/m^3] (soft tissue)

medium.blood_specific_heat = zeros(size(medium.density));
medium.blood_specific_heat((medium.density >= 1010 & medium.density <= dens_bone))  = 3620;   % [J/(kg.K)] (soft tissue)

medium.blood_perfusion_rate = zeros(size(medium.density));
medium.blood_perfusion_rate((medium.density >= 1010 & medium.density <= dens_bone))  = 0.008;   % [1/s] (soft tissue)

medium.blood_ambient_temperature = zeros(size(medium.density));
medium.blood_ambient_temperature((medium.density >= 1010 & medium.density <= dens_bone))  = 37;   % [degC] (soft tissue)

figure;
imagesc(medium.thermal_conductivity(:,:,int32(Nz/2)));
ylabel('x-position [mm]');
xlabel('y-position [mm]');
title('thermal conductivity');
c = colorbar;
ylabel(c, 'thermal conductivity');
axis image;

% create kWaveDiffusion object
kdiff = kWaveDiffusion(kgrid, medium, source, [], 'DisplayUpdates', false);
kdiff_2 = kWaveDiffusion(kgrid, medium, source, [], 'DisplayUpdates', false);
% set source on time and off time
on_time = pulse_dur; % [s]
off_time = pulse_rep_int - on_time; % [s]

% set time step size
dt = 0.01; % [s] 

% number of cycles
cycles = round(pulse_train_dur/pulse_rep_int); % 400cycles in 40sec

%% simulation
for i=1:cycles
    % take time steps
    kdiff.takeTimeStep(round(on_time / dt), dt);
    % turn off heat source and take time steps
    kdiff.Q = 0;
    kdiff.takeTimeStep(round(off_time / dt), dt);
    if rem(i,10)==0
        fprintf('cycle:%d/%d, maxT = %.3f degree\n',i,cycles,max(max(max(kdiff.T))));
    end
    kdiff.Q = kdiff_2.Q;
    
    if i==cycles %40s
       T1_40s = kdiff.T;      
    end        
end

%%
% =========================================================================
% VISUALISATION
% =========================================================================

% plot the acoustic pressure
figure;
imagesc(squeeze(p(round(Nx/2),:,:)) * 1e-6);
h = colorbar;
colormap(jet(256));
xlabel(h, '[MPa]');
ylabel('x-position [mm]');
xlabel('y-position [mm]');
axis image;
title(['Acoustic Pressure Amplitude : ',num2str(max(p(:) * 1e-6)),'[MPa]']);

% plot the volume rate of heat deposition
figure;
imagesc(squeeze(Q(round(Nx/2),:,:)) * 1e-7);
h = colorbar;
colormap(jet(256));
xlabel(h, '[kW/cm^2]');
ylabel('x-position [mm]');
xlabel('y-position [mm]');
axis image;
title('Volume Rate Of Heat Deposition');

% plot the temperature after heating
figure;
imagesc(squeeze(T1_40s(round(Nx/2),:,:)));
h = colorbar;
colormap(jet(256));
xlabel(h, '[degC]');
ylabel('x-position [mm]');
xlabel('y-position [mm]');
axis image;
title('Temperature After Heating');

% Overlap the figures
figure;
ax1 = axes; imagesc(ax1, imrotate(slice,90));
hold all;
ax2 = axes;
im2 = imagesc(ax2, imrotate(squeeze(T1_40s(round(Nx/2),:,:)),90));
im2.AlphaData = 0.5;
% ax3 = axes;
% im3 = imagesc(ax3, imrotate(squeeze(source.p_mask(round(Nx/2),:,:)),90));
% im3.AlphaData = 0.1;

linkaxes([ax1,ax2]); ax2.Visible = 'off'; ax2.XTick = []; ax2.YTick = [];
% ax3.Visible = 'off'; ax3.XTick = []; ax3.YTick = [];
colormap(ax1,'gray')
%     colormap(ax2,'turbo')
set([ax1,ax2],'Position',[.17 .11 .685 .815]);
cb2 = colorbar(ax2,'Position',[.85 .11 .0275 .815]);
xlabel(cb2, '[W/cm2]');
title(ax1,'Acoustic Pressure Amplitude')

% % plot thermal dose
% figure;
% imagesc(kdiff.cem43(60,:,:), [0, 1000]);
% h = colorbar;
% colormap(jet(256));
% xlabel(h, '[CEM43]');
% ylabel('x-position [mm]');
% xlabel('y-position [mm]');
% axis image;
% title('Thermal Dose');

% % plot lesion map
% figure;
% imagesc(kdiff.lesion_map(60,:,:), [0, 1]);
% colorbar;
% colormap(jet(256));
% ylabel('x-position [mm]');
% xlabel('y-position [mm]');
% axis image;
% title('Ablated Tissue');