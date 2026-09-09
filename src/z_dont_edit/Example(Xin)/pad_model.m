function [output_matrix] = pad_model(input_matrix, pad_size)
% Pad model to make space for positioning the transducer
% pad_size should be a 3*2 matrix
new_vol = zeros(size(input_matrix, 1) + pad_size(1,1) + pad_size(1,2), ...
    size(input_matrix, 2) + pad_size(2,1) + pad_size(2,2), ...
    size(input_matrix, 3) + pad_size(3,1) + pad_size(3,2));

new_vol = cast(new_vol, "like", input_matrix);
new_vol(pad_size(1,1) + 1:pad_size(1,1) + size(input_matrix, 1), ...
    pad_size(2,1) + 1:pad_size(2,1) + size(input_matrix, 2), ...
    pad_size(3,1) + 1:pad_size(3,1) + size(input_matrix, 3)) = input_matrix;

output_matrix = new_vol;
end