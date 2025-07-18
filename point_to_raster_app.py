"""
Point to Raster Conversion Tool with GUI
Converts point shapefiles to raster datasets for PGA, Richter, Wald, and SA values
Uses GeoPandas, Rasterio, and SciPy

Notes when processing:
- Humihingal na siya pag 5m yung cellsize, 5m cellsize = 25-30gb RAM Usage (most stable)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import warnings
from rasterio.mask import mask
import time
from datetime import datetime

warnings.filterwarnings('ignore')

# Check for required libraries
REQUIRED_LIBS = {
    'geopandas': 'GeoPandas',
    'rasterio': 'Rasterio',
    'shapely': 'Shapely',
    'pyproj': 'PyProj',
    'scipy': 'SciPy',
    'pyogrio': 'PyOgrio'
}

MISSING_LIBS = []
LIBS_AVAILABLE = True

for lib, name in REQUIRED_LIBS.items():
    try:
        __import__(lib)
    except ImportError:
        MISSING_LIBS.append(name)
        LIBS_AVAILABLE = False

if LIBS_AVAILABLE:
    import geopandas as gpd
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.features import rasterize
    from shapely.geometry import Point
    from scipy.spatial import cKDTree
    from scipy.interpolate import griddata


class PointToRasterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Point to Raster Conversion")
        self.root.geometry("850x800")
        self.root.resizable(True, True)

        # Variables
        self.input_shapefiles = []
        self.output_folder = tk.StringVar()
        self.processing = False

        # Default field names and cell sizes
        self.pga_field = tk.StringVar(value="PGA")
        self.richter_field = tk.StringVar(value="Richter_PE")
        self.wald_field = tk.StringVar(value="Wald_PEIS")
        self.sa_1_field = tk.StringVar(value="SA(1.0)")
        self.sa_02_field = tk.StringVar(value="SA(0.2)")
        self.pga_cellsize = tk.StringVar(value="0.00027451108")
        self.richter_cellsize = tk.StringVar(value="0.00027451108")
        self.wald_cellsize = tk.StringVar(value="0.00027451108")
        self.sa_1_cellsize = tk.StringVar(value="0.00027451108")
        self.sa_02_cellsize = tk.StringVar(value="0.00027451108")

        #Cellsize = refer to cell size of raster reference using GIS softwares
        # Bohol 9arc Cellsize reference = 0.0025178324
        # Bohol 5m CellSize = 0.00004556624

        # Interpolation method
        self.interpolation_method = tk.StringVar(value="bilinear")

        self.output_crs = tk.StringVar(value="EPSG:4326")  # Default WGS84
        self.use_input_crs = tk.BooleanVar(value=True)

        # Field selection toggles
        self.process_pga = tk.BooleanVar(value=True)
        self.process_richter = tk.BooleanVar(value=True)
        self.process_wald = tk.BooleanVar(value=True)
        self.process_sa_1 = tk.BooleanVar(value=True)
        self.process_sa_02 = tk.BooleanVar(value=True)

        # Clipping shapefile path
        self.clip_shapefile_path = tk.StringVar()

        self.setup_ui()
        self.check_libraries()

    def check_libraries(self):
        """Check if required libraries are available"""
        if not LIBS_AVAILABLE:
            missing_str = ", ".join(MISSING_LIBS)
            messagebox.showerror(
                "Required Libraries Missing",
                f"The following libraries are required but not installed:\n{missing_str}\n\n"
            )

    def setup_ui(self):
        """Setup the user interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Title
        title_label = ttk.Label(main_frame, text="Point to Raster Conversion",
                                font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        cred_label = ttk.Label(main_frame, text="by ACER-GS",
                                font=('Arial', 9, 'italic'))
        cred_label.grid(row=0, column=2, columnspan=1, pady=(0, 20))

        #cred_label = ttk.Label(main_frame, text="by ᜃᜒᜇᜓ K. Almoneda",
        #                        font=('Arial', 9, 'italic'))
        #cred_label.grid(row=0, column=2, columnspan=1, pady=(0, 20))

        # Input files section
        ttk.Label(main_frame, text="Input Shapefiles:", font=('Arial', 10, 'bold')).grid(
            row=1, column=0, sticky=tk.W, pady=(0, 5))

        # Listbox for input files
        listbox_frame = ttk.Frame(main_frame)
        listbox_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S),
                           pady=(0, 10))
        listbox_frame.columnconfigure(0, weight=1)
        listbox_frame.rowconfigure(0, weight=1)

        self.files_listbox = tk.Listbox(listbox_frame, height=6)
        self.files_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.files_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.files_listbox.configure(yscrollcommand=scrollbar.set)

        # Buttons for file management
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=2, sticky=(tk.N, tk.W), padx=(10, 0))

        ttk.Button(button_frame, text="Add Files", command=self.add_files).grid(
            row=0, column=0, pady=(0, 5), sticky=tk.W)
        ttk.Button(button_frame, text="Remove Selected", command=self.remove_selected_file).grid(
            row=1, column=0, pady=(0, 5), sticky=tk.W)
        ttk.Button(button_frame, text="Clear All", command=self.clear_all_files).grid(
            row=2, column=0, sticky=tk.W)

        # Output folder section
        ttk.Label(main_frame, text="Output Folder:", font=('Arial', 10, 'bold')).grid(
            row=3, column=0, sticky=tk.W, pady=(20, 5))

        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20))
        output_frame.columnconfigure(0, weight=1)

        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_folder)
        self.output_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))

        ttk.Button(output_frame, text="Browse", command=self.browse_output_folder).grid(
            row=0, column=1)

        # Interpolation method section
        interp_frame = ttk.LabelFrame(main_frame, text="Interpolation Method", padding="10")
        interp_frame.grid(row=5, column=0, columnspan=1, sticky=(tk.W, tk.E), pady=(0, 10), padx=(0, 5))

        ttk.Label(interp_frame, text="Method:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        interp_combo = ttk.Combobox(interp_frame, textvariable=self.interpolation_method, width=12)
        interp_combo['values'] = ('nearest', 'bilinear', 'cubic')
        interp_combo.grid(row=0, column=1, sticky=tk.W)

        # CRS selection section
        crs_frame = ttk.LabelFrame(main_frame, text="Coordinate Reference System", padding="10")
        crs_frame.grid(row=5, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        crs_frame.columnconfigure(1, weight=1)
        # Radio buttons for CRS options
        ttk.Radiobutton(crs_frame, text="Use input shapefile CRS",
                        variable=self.use_input_crs, value=True).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        ttk.Radiobutton(crs_frame, text="Use custom CRS:",
                        variable=self.use_input_crs, value=False).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 5))
        # CRS entry field
        self.crs_entry = ttk.Entry(crs_frame, textvariable=self.output_crs, width=15)
        self.crs_entry.grid(row=1, column=1, sticky=tk.W, padx=(5, 0))
        # Common CRS dropdown
        ttk.Label(crs_frame, text="Common CRS:").grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        crs_combo = ttk.Combobox(crs_frame, width=40, state="readonly")
        crs_combo['values'] = (
            'EPSG:4326 - WGS84 (Geographic)',
            'EPSG:3857 - Web Mercator',
            'EPSG:32651 - UTM Zone 51N (Philippines)',
            'EPSG:32652 - UTM Zone 52N (Philippines)',
            'EPSG:3123 - PRS92 / Philippines Zone I',
            'EPSG:3124 - PRS92 / Philippines Zone II',
            'EPSG:3125 - PRS92 / Philippines Zone III'
        )
        crs_combo.grid(row=2, column=1, sticky=tk.W, pady=(5, 0))
        # Bind combobox selection to update CRS entry
        def on_crs_select(event):
            selected = crs_combo.get()
            if selected:
                epsg_code = selected.split(' - ')[0]
                self.output_crs.set(epsg_code)
                self.use_input_crs.set(False)
        crs_combo.bind('<<ComboboxSelected>>', on_crs_select)

        # Parameters section
        params_frame = ttk.LabelFrame(main_frame, text="Value Fields & Cell Sizes", padding="10")
        params_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        # Field selection checkboxes
        params_frame.columnconfigure(2, weight=1)
        params_frame.columnconfigure(4, weight=1)

        # PGA parameters
        ttk.Checkbutton(params_frame, variable=self.process_pga).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Label(params_frame, text="PGA Field:").grid(row=0, column=1, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.pga_field, width=15).grid(
            row=0, column=2, sticky=(tk.W, tk.E), padx=(0, 20))
        ttk.Label(params_frame, text="Cell Size:").grid(row=0, column=3, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.pga_cellsize, width=15).grid(
            row=0, column=4, sticky=(tk.W, tk.E))

        # Richter parameters
        ttk.Checkbutton(params_frame, variable=self.process_richter).grid(row=1, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Label(params_frame, text="Richter Field:").grid(row=1, column=1, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.richter_field, width=15).grid(
            row=1, column=2, sticky=(tk.W, tk.E), padx=(0, 20))
        ttk.Label(params_frame, text="Cell Size:").grid(row=1, column=3, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.richter_cellsize, width=15).grid(
            row=1, column=4, sticky=(tk.W, tk.E))

        # Wald parameters
        ttk.Checkbutton(params_frame, variable=self.process_wald).grid(row=2, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Label(params_frame, text="Wald Field:").grid(row=2, column=1, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.wald_field, width=15).grid(
            row=2, column=2, sticky=(tk.W, tk.E), padx=(0, 20))
        ttk.Label(params_frame, text="Cell Size:").grid(row=2, column=3, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.wald_cellsize, width=15).grid(
            row=2, column=4, sticky=(tk.W, tk.E))

        # SA 1s parameters
        ttk.Checkbutton(params_frame, variable=self.process_sa_1).grid(row=3, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Label(params_frame, text="SA 1s Field:").grid(row=3, column=1, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.sa_1_field, width=15).grid(
            row=3, column=2, sticky=(tk.W, tk.E), padx=(0, 20))
        ttk.Label(params_frame, text="Cell Size:").grid(row=3, column=3, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.sa_1_cellsize, width=15).grid(
            row=3, column=4, sticky=(tk.W, tk.E))

        # SA 0.2s parameters
        ttk.Checkbutton(params_frame, variable=self.process_sa_02).grid(row=4, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Label(params_frame, text="SA 0.2s Field:").grid(row=4, column=1, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.sa_02_field, width=15).grid(
            row=4, column=2, sticky=(tk.W, tk.E), padx=(0, 20))
        ttk.Label(params_frame, text="Cell Size:").grid(row=4, column=3, sticky=tk.W)
        ttk.Entry(params_frame, textvariable=self.sa_02_cellsize, width=15).grid(
            row=4, column=4, sticky=(tk.W, tk.E))

        # Clipping shapefile section
        clip_frame = ttk.LabelFrame(main_frame, text="Clipping Tool", padding="10")
        clip_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 20))
        clip_frame.columnconfigure(1, weight=1)

        ttk.Label(clip_frame, text="Clipping Shapefile:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))

        # Container frame inside clip_frame
        clip_entry_frame = ttk.Frame(clip_frame)
        clip_entry_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 0))
        clip_entry_frame.columnconfigure(0, weight=1)

        # Entry field
        self.clip_entry = ttk.Entry(clip_entry_frame, textvariable=self.clip_shapefile_path)
        self.clip_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))

        # Browse button
        ttk.Button(clip_entry_frame, text="Browse", command=self.browse_clip_shapefile).grid(
            row=0, column=1, padx=(0, 5))

        # Clear clipping button
        ttk.Button(clip_entry_frame, text="Clear", command=self.clear_clip_shapefile).grid(
            row=0, column=2)

        # Process button
        self.process_button = ttk.Button(main_frame, text="Start Processing",
                                         command=self.start_processing)
        self.process_button.grid(row=8, column=0, columnspan=3, pady=(0, 20))

        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.grid(row=9, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        # Log output
        ttk.Label(main_frame, text="Processing Log:", font=('Arial', 10, 'bold')).grid(
            row=10, column=0, sticky=tk.W, pady=(10, 5))

        self.log_text = scrolledtext.ScrolledText(main_frame, height=10, width=80)
        self.log_text.grid(row=11, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S),
                           pady=(0, 10))

        # Configure row weights for resizing
        main_frame.rowconfigure(2, weight=1)
        main_frame.rowconfigure(11, weight=2)

    def add_files(self):
        """Add shapefile(s) to the input list"""
        files = filedialog.askopenfilenames(
            title="Select Point Shapefiles",
            filetypes=[("Shapefiles", "*.shp"), ("All files", "*.*")]
        )

        for file in files:
            if file not in self.input_shapefiles:
                self.input_shapefiles.append(file)
                self.files_listbox.insert(tk.END, os.path.basename(file))

    def remove_selected_file(self):
        """Remove selected file from the input list"""
        selection = self.files_listbox.curselection()
        if selection:
            index = selection[0]
            self.files_listbox.delete(index)
            del self.input_shapefiles[index]

    def clear_all_files(self):
        """Clear all files from the input list"""
        self.files_listbox.delete(0, tk.END)
        self.input_shapefiles.clear()

    def browse_output_folder(self):
        """Browse for output folder"""
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder.set(folder)

    def browse_clip_shapefile(self):
        """Browse for clipping shapefile"""
        file = filedialog.askopenfilename(
            title="Select Clipping Shapefile",
            filetypes=[("Shapefile", "*.shp"), ("All files", "*.*")]
        )
        if file:
            self.clip_shapefile_path.set(file)

    def clear_clip_shapefile(self):
        """Clear the clipping shapefile path"""
        self.clip_shapefile_path.set("")

    def log_message(self, message):
        """Add message to log"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.root.update()

    def timestamp(self):
        """Get formatted timestamp"""
        return datetime.now().strftime("%H:%M:%S")

    def validate_inputs(self):
        """Validate user inputs"""
        if not self.input_shapefiles:
            messagebox.showerror("Error", "Please select at least one input shapefile.")
            return False

        if not self.output_folder.get():
            messagebox.showerror("Error", "Please select an output folder.")
            return False

        if not os.path.exists(self.output_folder.get()):
            messagebox.showerror("Error", "Output folder does not exist.")
            return False

        # Check if at least one field is selected for processing
        if not any([self.process_pga.get(), self.process_richter.get(), self.process_wald.get(),
                    self.process_sa_1.get(), self.process_sa_02.get()]):
            messagebox.showerror("Error", "Please select at least one field to process.")
            return False

        # Validate clipping shapefile if specified
        if self.clip_shapefile_path.get():
            if not os.path.exists(self.clip_shapefile_path.get()):
                messagebox.showerror("Error", "Clipping shapefile does not exist.")
                return False

        # Validate CRS if custom CRS is selected
        if not self.use_input_crs.get():
            crs_code = self.output_crs.get().strip()
            if not crs_code:
                messagebox.showerror("Error", "Please specify a CRS or select 'Use input shapefile CRS'.")
                return False

            # Basic CRS format validation
            if not (crs_code.startswith('EPSG:') or crs_code.startswith('PROJ:')):
                messagebox.showwarning("Warning", "CRS should typically start with 'EPSG:' or 'PROJ:'")

        return True

    def validate_shapefile_structure(self, shapefile):
        """Validate shapefile structure"""
        try:
            gdf = gpd.read_file(shapefile, engine='pyogrio')

            # Check if it's a point shapefile
            if not all(gdf.geometry.geom_type == 'Point'):
                return False, "Shapefile must contain only point geometries"

            # Check which value fields exist
            available_fields = []
            field_mapping = {
                'pga': self.pga_field.get(),
                'richter': self.richter_field.get(),
                'wald': self.wald_field.get(),
                'sa_1': self.sa_1_field.get(),
                'sa_02': self.sa_02_field.get()
            }

            for field_type, field_name in field_mapping.items():
                if field_name in gdf.columns:
                    available_fields.append(field_type)

            if not available_fields:
                return False, "None of the specified value fields found in shapefile"

            return True, available_fields

        except Exception as e:
            return False, str(e)

    def create_raster_from_points(self, gdf, value_field, cell_size, output_path):
        """Create raster from point data using interpolation"""
        try:
            # Handle CRS transformation
            original_crs = gdf.crs

            if not self.use_input_crs.get():
                # User wants custom CRS
                try:
                    target_crs = self.output_crs.get().strip()
                    if target_crs and target_crs != str(original_crs):
                        self.log_message(f"    Transforming from {original_crs} to {target_crs}")
                        gdf = gdf.to_crs(target_crs)
                except Exception as e:
                    self.log_message(f"    Warning: CRS transformation failed - {e}")
                    self.log_message(f"    Using original CRS: {original_crs}")

            # Get bounds
            bounds = gdf.total_bounds

            # Calculate raster dimensions
            width = int((bounds[2] - bounds[0]) / cell_size) + 1
            height = int((bounds[3] - bounds[1]) / cell_size) + 1

            # Create coordinate arrays
            x = np.linspace(bounds[0], bounds[2], width)
            y = np.linspace(bounds[3], bounds[1], height)  # reverse Y to go top-down
            xx, yy = np.meshgrid(x, y)

            # Extract point coordinates and values
            points = np.column_stack([gdf.geometry.x, gdf.geometry.y])
            values = gdf[value_field].values

            # Remove NaN values
            valid_mask = ~np.isnan(values)
            points = points[valid_mask]
            values = values[valid_mask]

            if len(points) == 0:
                raise ValueError(f"No valid data points found for field {value_field}")

            # Interpolate values to grid
            grid_points = np.column_stack([xx.ravel(), yy.ravel()])

            interp_method = self.interpolation_method.get()
            if interp_method == "bilinear":
                interp_method = "linear"

            if interp_method == 'nearest':
                # Use nearest neighbor interpolation
                tree = cKDTree(points)
                distances, indices = tree.query(grid_points)
                grid_values = values[indices]
            else:
                # Use scipy griddata for linear/cubic interpolation
                grid_values = griddata(points, values, grid_points,
                                       method=interp_method,
                                       fill_value=np.nan)

            # Reshape to grid
            raster_data = grid_values.reshape(height, width)

            # Create transform
            transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3],
                                    width, height)

            # Write raster
            with rasterio.open(
                    output_path,
                    'w',
                    driver='GTiff',
                    height=height,
                    width=width,
                    count=1,
                    dtype=rasterio.float32,
                    crs=gdf.crs,
                    transform=transform,
                    compress='lzw'
            ) as dst:
                dst.write(raster_data.astype(rasterio.float32), 1)

            # Apply clipping if shapefile is specified
            if self.clip_shapefile_path.get():
                try:
                    clip_gdf = gpd.read_file(self.clip_shapefile_path.get(), engine="pyogrio")

                    # Ensure the clipping shapefile has the same CRS as the raster
                    if clip_gdf.crs != gdf.crs:
                        clip_gdf = clip_gdf.to_crs(gdf.crs)

                    with rasterio.open(output_path) as src:
                        out_image, out_transform = mask(
                            src,
                            clip_gdf.geometry,
                            crop=True,
                            nodata=np.nan
                        )
                        out_meta = src.meta.copy()
                        out_meta.update({
                            "height": out_image.shape[1],
                            "width": out_image.shape[2],
                            "transform": out_transform,
                            "nodata": np.nan
                        })

                    # Overwrite original with clipped version
                    with rasterio.open(output_path, 'w', **out_meta) as dst:
                        dst.write(out_image)

                    self.log_message(f"      Clipped raster using: {os.path.basename(self.clip_shapefile_path.get())}")

                except Exception as e:
                    self.log_message(f"      Warning: Clipping failed - {e}")

            return True

        except Exception as e:
            raise Exception(f"Error creating raster for {value_field}: {str(e)}")

    def start_processing(self):
        """Start the processing in a separate thread"""
        if not LIBS_AVAILABLE:
            messagebox.showerror("Error", "Required libraries are not available. Cannot process files.")
            return

        if not self.validate_inputs():
            return

        if self.processing:
            messagebox.showwarning("Warning", "Processing is already in progress.")
            return

        # Clear log
        self.log_text.delete(1.0, tk.END)

        # For elapsed time
        self.start_time = time.time()

        # Start processing thread
        thread = threading.Thread(target=self.process_files)
        thread.daemon = True
        thread.start()

    def process_files(self):
        """Process the shapefiles"""
        self.processing = True
        self.process_button.config(state='disabled')

        # Calculate total steps for the progress bar (files × selected fields per file)
        field_flags = [
            self.process_pga.get(), self.process_richter.get(),
            self.process_wald.get(), self.process_sa_1.get(), self.process_sa_02.get()
        ]
        fields_selected = sum(field_flags)
        total_steps = len(self.input_shapefiles) * fields_selected
        self.progress.config(mode='determinate', maximum=total_steps, value=0)

        try:
            self.log_message(f"{self.timestamp()} Starting point to raster conversion...")
            self.log_message(f"Output folder: {self.output_folder.get()}")
            self.log_message(f"Processing {len(self.input_shapefiles)} shapefile(s)...")
            self.log_message(f"Using {self.interpolation_method.get()} interpolation...")

            if self.clip_shapefile_path.get():
                self.log_message(f"Clipping enabled with: {os.path.basename(self.clip_shapefile_path.get())}")

            # Process each shapefile
            for i, shapefile in enumerate(self.input_shapefiles, 1):
                self.log_message(
                    f"\n{self.timestamp()} Processing {i}/{len(self.input_shapefiles)}: {os.path.basename(shapefile)}")

                try:
                    # Validate shapefile structure
                    is_valid, result = self.validate_shapefile_structure(shapefile)
                    if not is_valid:
                        self.log_message(f"  Error: {result}")
                        continue

                    available_fields = result
                    self.log_message(f"  Available fields: {', '.join(available_fields)}")

                    # Read shapefile
                    gdf = gpd.read_file(shapefile, engine="pyogrio")
                    self.log_message(f"  Loaded {len(gdf)} points from shapefile")

                    # Get base name for output rasters
                    base_name = Path(shapefile).stem

                    # Process each selected field
                    field_config = [
                        ('pga', self.process_pga.get(), self.pga_field.get(), self.pga_cellsize.get(), 'PGA'),
                        ('richter', self.process_richter.get(), self.richter_field.get(), self.richter_cellsize.get(),
                         'Richter'),
                        ('wald', self.process_wald.get(), self.wald_field.get(), self.wald_cellsize.get(), 'Wald'),
                        ('sa_1', self.process_sa_1.get(), self.sa_1_field.get(), self.sa_1_cellsize.get(), 'SA1'),
                        ('sa_02', self.process_sa_02.get(), self.sa_02_field.get(), self.sa_02_cellsize.get(), 'SA02')
                    ]

                    for field_key, process_field, field_name, cell_size, output_suffix in field_config:
                        if process_field and field_key in available_fields:
                            self.log_message(f"  Converting {field_name} field...")
                            output_path = os.path.join(self.output_folder.get(),
                                                       f"{base_name}_{output_suffix}_raster.tif")
                            self.create_raster_from_points(gdf, field_name, float(cell_size), output_path)
                            self.log_message(f"    Created: {base_name}_{output_suffix}_raster.tif")
                            self.progress.step()
                            self.root.update_idletasks()

                except Exception as e:
                    self.log_message(f"  Error processing {os.path.basename(shapefile)}: {str(e)}")

            elapsed = time.time() - self.start_time
            self.log_message(f"\n{self.timestamp()} Processing completed in {elapsed:.2f} seconds!")
            self.log_message(f"Output saved to: {self.output_folder.get()}")

            messagebox.showinfo("Success",
                                f"Processing completed successfully!\nOutput saved to: {self.output_folder.get()}")

        except Exception as e:
            error_msg = f"An error occurred during processing: {str(e)}"
            self.log_message(f"\nERROR: {error_msg}")
            messagebox.showerror("Error", error_msg)

        finally:
            self.processing = False
            self.process_button.config(state='normal')
            self.progress.stop()
            #self.progress['value'] = 0


def main():
    """Main function to run the application"""
    root = tk.Tk()
    app = PointToRasterGUI(root)

    # Set window size and center it
    width = 650
    height = 850
    root.geometry(f"{width}x{height}")

    # Center the window
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    root.mainloop()

if __name__ == '__main__':
    main()
